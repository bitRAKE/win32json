#!/usr/bin/env python3
"""Convert win32json metadata into fasm2 include files and verify the result."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


ARCH_TAGS = {"x86": "X86", "x64": "X64", "arm64": "Arm64"}
POINTER_SIZE = {"x86": 4, "x64": 8, "arm64": 8}

NATIVE = {
    "Byte": (1, 1, "db"),
    "SByte": (1, 1, "db"),
    "Boolean": (1, 1, "db"),
    "UInt16": (2, 2, "dw"),
    "Int16": (2, 2, "dw"),
    "Char": (2, 2, "dw"),
    "UInt32": (4, 4, "dd"),
    "Int32": (4, 4, "dd"),
    "Single": (4, 4, "dd"),
    "UInt64": (8, 8, "dq"),
    "Int64": (8, 8, "dq"),
    "Double": (8, 8, "dq"),
    "Guid": (16, 4, "GUID"),
    "Void": (0, 1, None),
}

TYPE_KINDS = {
    "Struct",
    "Union",
    "Enum",
    "NativeTypedef",
    "FunctionPointer",
    "Com",
    "ComClassID",
}

UUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)


@dataclass(frozen=True)
class TypeKey:
    api: str
    path: tuple[str, ...]


@dataclass
class TypeDecl:
    api: str
    name: str
    kind: str
    item: dict[str, Any]
    key: TypeKey
    parent: TypeKey | None
    order: int
    emitted: str = ""


@dataclass
class SymbolDecl:
    raw: str
    kind: str
    api: str
    owner: str
    order: int
    emitted: str = ""
    reason: str = ""


@dataclass
class GuidExport:
    label: str
    guid: str
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Layout:
    size: int
    align: int
    directive: str | None = None
    type_name: str | None = None
    comment: str = ""


@dataclass
class FieldLayout:
    name: str
    type_expr: dict[str, Any]
    layout: Layout
    offset: int
    size: int
    align: int
    render: str
    comment: str


@dataclass
class RecordLayout:
    size: int
    align: int
    fields: list[FieldLayout]
    is_union: bool


@dataclass
class ModelStats:
    json_files: int = 0
    constants: int = 0
    uuid_constants: int = 0
    property_keys: int = 0
    string_constants: int = 0
    enum_values: int = 0
    types: Counter[str] = field(default_factory=Counter)
    functions: int = 0
    unicode_aliases: int = 0
    flexible_arrays: int = 0
    unresolved_refs: Counter[str] = field(default_factory=Counter)
    renamed_symbols: int = 0


def align_up(value: int, alignment: int) -> int:
    if alignment <= 1:
        return value
    return (value + alignment - 1) & -alignment


# Collision handling, driven by tests/fasm2-collision (probe every win32json
# name that also appears as a token in the fasm2 include tree against fasmg,
# in definition / ?-prefixed definition / expression-reference / struct-field
# contexts). Three classes emerged:
#
# 1. Line-start interception (directives, instructions, macros: Match, Add,
#    Format, fScale, ...). Harmless when the definition is written with the
#    fasmg `?` prefix (`?Match = 0Fh`), which forces symbol interpretation;
#    bare references and dotted field access then work with the original
#    name. All constant/enum and struct-field definitions are emitted
#    ?-prefixed, so this class needs no renaming at all.
#
# 2. Expression-level names: predefined register/element symbols (Eax, R8,
#    cx, Byte, at, From, ...) where a definition SILENTLY clobbers the
#    element, and operators / circular symbolics (string, format, align,
#    Float) where bare references misparse. Only renaming (`_` postfix)
#    helps; the `?` prefix does not protect references.
#
# 3. Struct-name shadowing: the struct/ends macro pair defines a line-start
#    macro per struct name, so a *type* whose name matches a directive or
#    macro (MONITOR, SECTION, STRING) would shadow it from the declaration
#    onward; types additionally get class-1 names renamed.

# Exact spellings that probed as class 2 (verdict "rename" in
# tests/fasm2-collision/full_report.tsv).
RENAME_EXACT = frozenset(
    "Align Byte CS CX Cs DS DUP DWord DX Ds Dword Eax Ebp Ebx Ecx Edi Edx Eip"
    " Element End Es Esi Esp Float From GS MetaData Metadata R10 R11 R12 R13"
    " R14 R15 R8 R9 Rax Rbp Rbx Rcx Rdi Rdx Rip Rsi Rsp STRING Scale Sp"
    " String Word Xmm0 Xmm1 Xmm2 Xmm3 align at ch cl cx dx eDx element end"
    " format from fs scale si st string".split()
)


def _register_family() -> frozenset[str]:
    names = set(
        "al cl dl bl ah ch dh bh spl bpl sil dil"
        " ax cx dx bx sp bp si di ip"
        " eax ecx edx ebx esp ebp esi edi eip"
        " rax rcx rdx rbx rsp rbp rsi rdi rip"
        " cs ds es fs gs ss st".split()
    )
    names.update(f"r{i}{s}" for i in range(8, 16) for s in ("", "b", "w", "d"))
    names.update(f"{p}{i}" for p in ("xmm", "ymm", "zmm") for i in range(32))
    names.update(f"{p}{i}" for p in ("mm", "tmm", "st") for i in range(8))
    names.update(f"k{i}" for i in range(8))
    names.update(f"{p}{i}" for p in ("cr", "dr") for i in range(16))
    names.update(f"bnd{i}" for i in range(4))
    return frozenset(names)


# Class-2 stems that are case-insensitive in fasmg/fasm2 (register and size
# elements, expression operators, special symbolics), completing the probed
# exact spellings for names future win32json revisions might add.
RENAME_CASELESS = _register_family() | frozenset(
    "byte word dword fword pword qword tbyte tword dqword xword qqword yword"
    " dqqword zword"
    " at dup from eq eqtype relativeto defined definite used mod not and or"
    " xor shl shr string sizeof lengthof elementsof elementof scaleof"
    " metadataof trunc float bappend"
    " element end align format scale metadata".split()
)

# Class-1 exact spellings (verdict "qpfx"): fine for ?-prefixed constants,
# but as a STRUCT NAME they would shadow the intercepting directive, macro,
# or instruction, so type declarations rename these too.
LINESTART_EXACT = frozenset(
    "Add add bitmap Break Call CpuId cursor du dw DW Enter err file File"
    " Format frame Frame fScale icon Import In Inc Int Invoke Label Leave"
    " Library load Load Local Lock Looped Match MONITOR monitor Monitor"
    " NameSpace nameSpace Out out pause Pause Pop Postpone Prefetch PROC"
    " Purge Push rcl RESTORE restore Restore RP Rp SECTION Section Serialize"
    " Store str Str Use Virtual Wait".split()
)

# Case-insensitive fasmg directives and fasm2 macro-layer names, as a safety
# net for future type names (same shadowing concern as LINESTART_EXACT).
LINESTART_CASELESS = frozenset(
    "db dd dp dq dt ddq dqq dbx rb rw rd rq rt if else while repeat iterate"
    " irp irpv indx macro struc esc purge restruc define redefine equ reequ"
    " postpone calminstruction eval include org assert display ends union"
    " struct import api endp locals endl heap ccall cinvoke stdcall comcall"
    " cominvk menu dialog label section virtual match rmatch namespace err"
    " break local restore store file".split()
)


# Struct fields are emitted ?-prefixed and land in the instance namespace,
# which shields every collision class above — except `at`: a field label
# named `at` poisons the union machinery's own `virtual at union` statements
# ("invalid or inaccessible addressing area"). The only fld_qpfx failure in
# the full tests/fasm2-collision sweep.
FIELD_RENAME_CASELESS = frozenset(("at",))


def field_emit_name(name: str) -> str:
    return name + "_" if name.lower() in FIELD_RENAME_CASELESS else name


def is_rename(name: str) -> bool:
    return name in RENAME_EXACT or name.lower() in RENAME_CASELESS


def is_type_rename(name: str) -> bool:
    return (
        is_rename(name)
        or name in LINESTART_EXACT
        or name.lower() in LINESTART_CASELESS
    )


def sanitize_identifier(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_?@$]", "_", text)
    if not text or not re.match(r"[A-Za-z_?@$]", text[0]):
        text = "_" + text
    return text


def api_prefix(api: str) -> str:
    return sanitize_identifier(api.replace(".", "_"))


def dll_alias_name(dll: str) -> str:
    stem = dll
    if stem.lower().endswith(".dll"):
        stem = stem[:-4]
    return sanitize_identifier(stem.replace("-", "_").replace(".", "_")).lower()


def is_apiset_dll(dll: str) -> bool:
    return dll.lower().startswith(("api-ms-", "ext-ms-"))


def fasm_quote(text: str) -> str:
    if "'" in text and '"' not in text:
        return f'"{text}"'
    if "'" in text:
        text = text.replace("'", "''")
    return f"'{text}'"


def fasm_string(text: str) -> str:
    # Bytes below 0x20 cannot appear inside fasmg quoted strings; emit them as
    # numeric list items between quoted runs: 'some',0,'text'
    parts: list[str] = []
    run: list[str] = []
    for ch in text:
        if ord(ch) >= 0x20:
            run.append(ch)
            continue
        if run:
            parts.append(fasm_quote("".join(run)))
            run = []
        parts.append(fasm_int(ord(ch)))
    if run:
        parts.append(fasm_quote("".join(run)))
    if not parts:
        return "''"
    return ",".join(parts)


def fasm_int(value: int) -> str:
    if value < 0:
        return str(value)
    if value < 10:
        return str(value)
    digits = f"{value:X}"
    if digits[0].isalpha():
        digits = "0" + digits
    return f"{digits}h"


def fasm_value(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return fasm_int(value)
    if isinstance(value, float):
        return format(value, ".9g")
    if isinstance(value, str):
        return fasm_string(value)
    raise ValueError(f"unsupported constant value: {value!r}")


def uuid_ddq(guid_text: str) -> str:
    value = int.from_bytes(uuid.UUID(guid_text).bytes_le, "little")
    return f"0x{value:032X}"


def is_uuid_text(value: Any) -> bool:
    return isinstance(value, str) and UUID_RE.fullmatch(value) is not None


def include_arch(item: dict[str, Any], arch: str) -> bool:
    arches = item.get("Architectures") or []
    return not arches or ARCH_TAGS[arch] in arches


def is_type_expr(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("Kind"), str)


class Win32JsonModel:
    def __init__(self, api_dir: Path, arch: str):
        self.api_dir = api_dir
        self.root = api_dir.parent
        self.arch = arch
        self.ptr_size = POINTER_SIZE[arch]
        self.ptr_directive = "dd" if self.ptr_size == 4 else "dq"
        self.stats = ModelStats()

        self.api_data: dict[str, dict[str, Any]] = {}
        self.constants: list[dict[str, Any]] = []
        self.uuid_constants: list[dict[str, Any]] = []
        self.property_keys: list[dict[str, Any]] = []
        self.functions: list[dict[str, Any]] = []
        self.unicode_aliases: dict[str, set[str]] = defaultdict(set)
        self.types: list[TypeDecl] = []
        self.type_by_key: dict[TypeKey, TypeDecl] = {}
        self.top_type_by_api_name: dict[tuple[str, str], TypeDecl] = {}
        self.nested_by_parent_name: dict[tuple[TypeKey, str], TypeDecl] = {}

        self.symbols: list[SymbolDecl] = []
        self.type_symbol: dict[TypeKey, SymbolDecl] = {}
        self.constant_symbol: dict[int, SymbolDecl] = {}
        self.uuid_symbol: dict[int, SymbolDecl] = {}
        self.property_symbol: dict[int, SymbolDecl] = {}
        self.function_symbol: dict[int, SymbolDecl] = {}
        self.enum_symbol: dict[tuple[TypeKey, str, int], SymbolDecl] = {}
        self.guid_exports: dict[str, GuidExport] = {}
        self.guid_export_conflicts: dict[str, dict[str, list[str]]] = {}

        self._record_layouts: dict[TypeKey, RecordLayout] = {}
        self._layout_visiting: set[TypeKey] = set()
        self._com_method_cache: dict[TypeKey, list[str]] = {}

    def load(self) -> None:
        files = sorted(self.api_dir.glob("*.json"))
        self.stats.json_files = len(files)
        order = 0
        for path in files:
            api = path.stem
            data = json.loads(path.read_text(encoding="utf-8"))
            self.api_data[api] = data

            for item in data.get("Constants", []) or []:
                clone = dict(item)
                clone["_api"] = api
                clone["_order"] = order
                order += 1
                if clone.get("ValueType") == "PropertyKey":
                    self.property_keys.append(clone)
                    self.stats.property_keys += 1
                elif is_uuid_text(clone.get("Value")):
                    self.uuid_constants.append(clone)
                    self.stats.uuid_constants += 1
                else:
                    self.constants.append(clone)
                    self.stats.constants += 1
                    if isinstance(clone.get("Value"), str):
                        self.stats.string_constants += 1

            for item in data.get("Types", []) or []:
                if include_arch(item, self.arch):
                    self._add_type(api, item, None, (item["Name"],), order)
                    order += 1

            for item in data.get("Functions", []) or []:
                if include_arch(item, self.arch):
                    clone = dict(item)
                    clone["_api"] = api
                    clone["_order"] = order
                    order += 1
                    self.functions.append(clone)
                    self.stats.functions += 1

            aliases = data.get("UnicodeAliases", []) or []
            self.stats.unicode_aliases += len(aliases)
            for name in aliases:
                self.unicode_aliases[api].add(name)

        self._build_symbols()
        self._compute_all_layouts()

    def load_guid_exports(self, roots: Iterable[Path]) -> None:
        labels = {
            f"IID_{decl.emitted}"
            for decl in self.types
            if decl.kind == "Com" and not decl.item.get("Guid")
        }
        self.guid_exports, self.guid_export_conflicts = scan_guid_export_roots(labels, roots)

    def _add_type(
        self,
        api: str,
        item: dict[str, Any],
        parent: TypeKey | None,
        path: tuple[str, ...],
        order: int,
    ) -> TypeDecl:
        key = TypeKey(api, path)
        decl = TypeDecl(api, item["Name"], item["Kind"], item, key, parent, order)
        self.types.append(decl)
        self.type_by_key[key] = decl
        self.stats.types[decl.kind] += 1
        if parent is None:
            self.top_type_by_api_name[(api, decl.name)] = decl
        else:
            self.nested_by_parent_name[(parent, decl.name)] = decl

        for index, nested in enumerate(item.get("NestedTypes", []) or [], 1):
            if include_arch(nested, self.arch):
                nested_path = (*path, f"{nested['Name']}#{index}")
                self._add_type(api, nested, key, nested_path, order)
        return decl

    def _build_symbols(self) -> None:
        order = 0
        for index, item in enumerate(self.constants):
            sym = SymbolDecl(item["Name"], "constant", item["_api"], "", order)
            self.constant_symbol[index] = sym
            self.symbols.append(sym)
            order += 1

        for index, item in enumerate(self.uuid_constants):
            sym = SymbolDecl(item["Name"], "uuid", item["_api"], "", order)
            self.uuid_symbol[index] = sym
            self.symbols.append(sym)
            order += 1

        for index, item in enumerate(self.property_keys):
            sym = SymbolDecl(item["Name"], "property_key", item["_api"], "", order)
            self.property_symbol[index] = sym
            self.symbols.append(sym)
            order += 1

        for decl in self.types:
            if decl.parent is None:
                sym = SymbolDecl(decl.name, "type", decl.api, decl.kind, order)
                self.type_symbol[decl.key] = sym
                self.symbols.append(sym)
                order += 1

                if decl.kind == "Enum":
                    for value_index, value in enumerate(decl.item.get("Values", []) or []):
                        enum_sym = SymbolDecl(
                            value["Name"],
                            "enum_value",
                            decl.api,
                            decl.name,
                            order,
                        )
                        self.enum_symbol[(decl.key, value["Name"], value_index)] = enum_sym
                        self.symbols.append(enum_sym)
                        self.stats.enum_values += 1
                        order += 1

        dll_aliases = self.dll_aliases()
        for index, item in enumerate(self.functions):
            owner = dll_aliases[item["DllImport"]]
            sym = SymbolDecl(item["Name"], "function", item["_api"], owner, order)
            self.function_symbol[index] = sym
            self.symbols.append(sym)
            order += 1

        by_raw: dict[str, list[SymbolDecl]] = defaultdict(list)
        for sym in self.symbols:
            by_raw[sym.raw].append(sym)

        def sym_rename(sym: SymbolDecl, name: str) -> bool:
            # types become struct/interface macros, so line-start
            # interceptor names would get shadowed by the declaration
            return is_type_rename(name) if sym.kind == "type" else is_rename(name)

        used: set[str] = set()
        for raw, group in sorted(by_raw.items(), key=lambda pair: min(s.order for s in pair[1])):
            if len(group) == 1 and raw not in used and not sym_rename(group[0], raw):
                group[0].emitted = raw
                used.add(raw)
                continue

            for sym in sorted(group, key=lambda s: s.order):
                base = self._conflict_name(sym) if len(group) > 1 else raw
                if sym_rename(sym, base):
                    base = base + "_"
                    reason = "renamed to avoid fasm2 reserved name"
                else:
                    reason = "renamed to avoid flat fasm2 symbol collision"
                name = base
                suffix = 2
                while name in used:
                    name = f"{base}__{suffix}"
                    suffix += 1
                sym.emitted = name
                sym.reason = reason
                used.add(name)
                self.stats.renamed_symbols += 1

        for decl in self.types:
            if decl.parent is None:
                decl.emitted = self.type_symbol[decl.key].emitted
            else:
                parent = self.type_by_key[decl.parent]
                stem = decl.name.lstrip("_") or decl.name
                decl.emitted = sanitize_identifier(f"{parent.emitted}__{stem}")
                if is_type_rename(decl.emitted):
                    decl.emitted += "_"
                base = decl.emitted
                suffix = 2
                while decl.emitted in used:
                    decl.emitted = f"{base}__{suffix}"
                    suffix += 1
                used.add(decl.emitted)

    def _conflict_name(self, sym: SymbolDecl) -> str:
        if sym.kind == "enum_value":
            return sanitize_identifier(f"{api_prefix(sym.api)}__{sym.owner}__{sym.raw}")
        if sym.kind == "function":
            return sanitize_identifier(f"{sym.owner}__{sym.raw}")
        if sym.kind == "constant":
            return sanitize_identifier(f"{api_prefix(sym.api)}__{sym.raw}__CONST")
        if sym.kind == "uuid":
            return sanitize_identifier(f"{api_prefix(sym.api)}__{sym.raw}__UUID")
        if sym.kind == "property_key":
            return sanitize_identifier(f"{api_prefix(sym.api)}__{sym.raw}__PKEY")
        return sanitize_identifier(f"{api_prefix(sym.api)}__{sym.raw}")

    def dll_aliases(self) -> dict[str, str]:
        # exact-name tiebreak: case variants like RstrtMgr.dll/rstrtmgr.dll
        # otherwise land in hash-randomized set order, flipping which one
        # gets the _2 alias between runs
        dlls = sorted({item["DllImport"] for item in self.functions}, key=lambda dll: (dll.lower(), dll))
        used: set[str] = set()
        aliases: dict[str, str] = {}
        for dll in dlls:
            base = dll_alias_name(dll)
            alias = base
            suffix = 2
            while alias in used:
                alias = f"{base}_{suffix}"
                suffix += 1
            used.add(alias)
            aliases[dll] = alias
        return aliases

    def resolve_apiref(self, expr: dict[str, Any], context: TypeDecl | None) -> TypeDecl | None:
        api = expr.get("Api")
        name = expr.get("Name")
        if not api or not name:
            return None

        cursor = context
        while cursor is not None and cursor.api == api:
            nested = self.nested_by_parent_name.get((cursor.key, name))
            if nested:
                return nested
            cursor = self.type_by_key.get(cursor.parent) if cursor.parent else None

        return self.top_type_by_api_name.get((api, name))

    def _pointer_layout(self) -> Layout:
        return Layout(self.ptr_size, self.ptr_size, self.ptr_directive, comment="pointer")

    def type_expr_layout(self, expr: dict[str, Any], context: TypeDecl | None) -> Layout:
        kind = expr.get("Kind")
        if kind == "Native":
            name = expr.get("Name")
            if name in ("IntPtr", "UIntPtr", "String"):
                return self._pointer_layout()
            if name not in NATIVE:
                self.stats.unresolved_refs[f"Native:{name}"] += 1
                return Layout(1, 1, "db", comment=f"unresolved native {name}")
            size, align, directive = NATIVE[name]
            if directive == "GUID":
                return Layout(size, align, type_name="WIN32JSON_GUID", comment="Guid")
            return Layout(size, align, directive, comment=name)

        if kind in ("PointerTo", "LPArray", "MissingClrType"):
            return self._pointer_layout()

        if kind == "Array":
            child = self.type_expr_layout(expr["Child"], context)
            shape = expr.get("Shape") or {}
            count = shape.get("Size")
            if count is None:
                count = 1
                self.stats.flexible_arrays += 1
            return Layout(child.size * count, child.align, comment=f"{count} x {child.comment}")

        if kind == "ApiRef":
            decl = self.resolve_apiref(expr, context)
            if decl is None:
                self.stats.unresolved_refs[f"{expr.get('Api')}:{expr.get('Name')}"] += 1
                return self._pointer_layout()
            if decl.kind in ("Struct", "Union"):
                rec = self.record_layout(decl)
                return Layout(rec.size, rec.align, type_name=decl.emitted, comment=decl.name)
            if decl.kind == "Enum":
                base = decl.item.get("IntegerBase") or "UInt32"
                size, align, directive = NATIVE.get(base, NATIVE["UInt32"])
                return Layout(size, align, directive, comment=decl.name)
            if decl.kind == "NativeTypedef":
                return self.type_expr_layout(decl.item["Def"], decl)
            if decl.kind in ("FunctionPointer", "Com", "ComClassID"):
                return self._pointer_layout()
            self.stats.unresolved_refs[f"{decl.api}:{decl.name}:{decl.kind}"] += 1
            return self._pointer_layout()

        self.stats.unresolved_refs[f"Kind:{kind}"] += 1
        return Layout(1, 1, "db", comment=f"unresolved kind {kind}")

    def record_layout(self, decl: TypeDecl) -> RecordLayout:
        if decl.key in self._record_layouts:
            return self._record_layouts[decl.key]
        if decl.key in self._layout_visiting:
            self.stats.unresolved_refs[f"cycle:{decl.api}:{decl.name}"] += 1
            return RecordLayout(self.ptr_size, self.ptr_size, [], decl.kind == "Union")

        self._layout_visiting.add(decl.key)
        pack = decl.item.get("PackingSize") or 0
        is_union = decl.kind == "Union"
        fields: list[FieldLayout] = []
        offset = 0
        max_align = 1
        max_size = 0

        for field in decl.item.get("Fields", []) or []:
            layout = self.type_expr_layout(field["Type"], decl)
            effective_align = layout.align
            if pack:
                effective_align = min(effective_align, pack)
            effective_align = max(1, effective_align)
            max_align = max(max_align, effective_align)

            if is_union:
                field_offset = 0
                max_size = max(max_size, layout.size)
            else:
                offset = align_up(offset, effective_align)
                field_offset = offset
                offset += layout.size

            field_name = field_emit_name(field["Name"])
            field_comment = layout.comment
            if field_name != field["Name"]:
                field_comment = f"{field_comment} (renamed from {field['Name']})"
            fields.append(
                FieldLayout(
                    name=field_name,
                    type_expr=field["Type"],
                    layout=layout,
                    offset=field_offset,
                    size=layout.size,
                    align=effective_align,
                    render=self.render_field_storage(field["Type"], layout, decl),
                    comment=field_comment,
                )
            )

        if is_union:
            size = align_up(max_size, max_align)
        else:
            size = align_up(offset, max_align)

        record = RecordLayout(size, max_align, fields, is_union)
        self._record_layouts[decl.key] = record
        self._layout_visiting.remove(decl.key)
        return record

    def render_field_storage(self, expr: dict[str, Any], layout: Layout, context: TypeDecl) -> str:
        if expr.get("Kind") == "Array":
            shape = expr.get("Shape") or {}
            count = shape.get("Size") or 1
            child = self.type_expr_layout(expr["Child"], context)
            if child.directive:
                return f"{child.directive} {count} dup (?)"
            return f"db {layout.size} dup (?)"

        if layout.type_name:
            return layout.type_name
        if layout.directive:
            return f"{layout.directive} ?"
        return f"db {layout.size} dup (?)"

    def _compute_all_layouts(self) -> None:
        for decl in self.types:
            if decl.kind in ("Struct", "Union"):
                self.record_layout(decl)

    def type_dependencies(self, decl: TypeDecl) -> set[TypeKey]:
        deps: set[TypeKey] = set()
        if decl.kind not in ("Struct", "Union"):
            return deps

        def walk(expr: dict[str, Any], pointer_depth: int = 0) -> None:
            kind = expr.get("Kind")
            if kind in ("PointerTo", "LPArray"):
                child = expr.get("Child")
                if is_type_expr(child):
                    walk(child, pointer_depth + 1)
                return
            if kind == "Array":
                child = expr.get("Child")
                if is_type_expr(child):
                    walk(child, pointer_depth)
                return
            if kind == "ApiRef" and pointer_depth == 0:
                target = self.resolve_apiref(expr, decl)
                if target and target.kind in ("Struct", "Union") and target.key != decl.key:
                    deps.add(target.key)

        for field in decl.item.get("Fields", []) or []:
            walk(field["Type"])
        return deps

    def ordered_types(self) -> list[TypeDecl]:
        records = [decl for decl in self.types if decl.kind in ("Struct", "Union")]
        non_records = [decl for decl in self.types if decl.kind not in ("Struct", "Union")]

        record_keys = {decl.key for decl in records}
        deps = {decl.key: self.type_dependencies(decl) & record_keys for decl in records}
        dependents: dict[TypeKey, set[TypeKey]] = defaultdict(set)
        indegree: dict[TypeKey, int] = {}
        for key, key_deps in deps.items():
            indegree[key] = len(key_deps)
            for dep in key_deps:
                dependents[dep].add(key)

        by_key = {decl.key: decl for decl in records}
        source_order = {decl.key: index for index, decl in enumerate(records)}

        def record_order(key: TypeKey) -> tuple[int, int]:
            return by_key[key].order, source_order[key]

        ready = deque(sorted((key for key, degree in indegree.items() if degree == 0), key=record_order))
        ordered_record_keys: list[TypeKey] = []
        while ready:
            key = ready.popleft()
            ordered_record_keys.append(key)
            for dependent in sorted(dependents[key], key=record_order):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)

        if len(ordered_record_keys) != len(records):
            remaining = [key for key in record_keys if key not in set(ordered_record_keys)]
            for key in sorted(remaining, key=record_order):
                self.stats.unresolved_refs[f"type-order-cycle:{by_key[key].api}:{by_key[key].name}"] += 1
                ordered_record_keys.append(key)

        ordered_records = [by_key[key] for key in ordered_record_keys]
        return ordered_records + non_records

    def com_methods(self, decl: TypeDecl) -> list[str]:
        if decl.key in self._com_method_cache:
            return self._com_method_cache[decl.key]
        methods: list[str] = []
        base_expr = decl.item.get("Interface")
        if is_type_expr(base_expr):
            base = self.resolve_apiref(base_expr, decl)
            if base and base.kind == "Com":
                methods.extend(self.com_methods(base))
        for method in decl.item.get("Methods", []) or []:
            if include_arch(method, self.arch):
                methods.append(method["Name"])
        # COM method overloads share a name; the interface macro defines a
        # label per method, so number the repeats: Name, Name__2, Name__3 ...
        seen: dict[str, int] = {}
        taken = set(methods)
        for index, name in enumerate(methods):
            count = seen.get(name, 0) + 1
            seen[name] = count
            if count > 1:
                candidate = f"{name}__{count}"
                while candidate in taken:
                    count += 1
                    candidate = f"{name}__{count}"
                seen[name] = count
                methods[index] = candidate
                taken.add(candidate)
        self._com_method_cache[decl.key] = methods
        return methods


def tsv_cell(value: Any) -> str:
    text = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return text if text else "-"


def read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


class PEImage:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        self.sections: list[tuple[int, int, int, int]] = []
        self.export_rva = 0
        self.export_size = 0
        self._parse()

    def _parse(self) -> None:
        data = self.data
        if len(data) < 0x100 or data[:2] != b"MZ":
            raise ValueError("not a PE image")
        pe_offset = read_u32(data, 0x3C)
        if pe_offset + 4 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
            raise ValueError("not a PE image")
        coff = pe_offset + 4
        section_count = read_u16(data, coff + 2)
        optional_size = read_u16(data, coff + 16)
        optional = coff + 20
        magic = read_u16(data, optional)
        data_directory = optional + (112 if magic == 0x20B else 96)
        if data_directory + 8 > len(data):
            raise ValueError("invalid PE image")
        self.export_rva = read_u32(data, data_directory)
        self.export_size = read_u32(data, data_directory + 4)
        section_offset = optional + optional_size
        for index in range(section_count):
            offset = section_offset + index * 40
            if offset + 40 > len(data):
                break
            virtual_size = read_u32(data, offset + 8)
            virtual_address = read_u32(data, offset + 12)
            raw_size = read_u32(data, offset + 16)
            raw_offset = read_u32(data, offset + 20)
            self.sections.append((virtual_address, max(virtual_size, raw_size), raw_offset, raw_size))

    def rva_offset(self, rva: int) -> int | None:
        for virtual_address, virtual_size, raw_offset, raw_size in self.sections:
            if virtual_address <= rva < virtual_address + virtual_size:
                delta = rva - virtual_address
                if delta < raw_size:
                    return raw_offset + delta
                return None
        return None

    def read_c_string(self, rva: int) -> str:
        offset = self.rva_offset(rva)
        if offset is None:
            raise ValueError("invalid string RVA")
        end = self.data.index(0, offset)
        return self.data[offset:end].decode("ascii", errors="replace")

    def exports(self) -> dict[str, int]:
        if not self.export_rva:
            return {}
        offset = self.rva_offset(self.export_rva)
        if offset is None:
            return {}
        data = self.data
        name_count = read_u32(data, offset + 24)
        functions_rva = read_u32(data, offset + 28)
        names_rva = read_u32(data, offset + 32)
        ordinals_rva = read_u32(data, offset + 36)
        functions = self.rva_offset(functions_rva)
        names = self.rva_offset(names_rva)
        ordinals = self.rva_offset(ordinals_rva)
        if functions is None or names is None or ordinals is None:
            return {}

        result: dict[str, int] = {}
        for index in range(name_count):
            try:
                name_rva = read_u32(data, names + index * 4)
                name = self.read_c_string(name_rva)
                ordinal = read_u16(data, ordinals + index * 2)
                export_rva = read_u32(data, functions + ordinal * 4)
            except Exception:
                continue
            result[name] = export_rva
        return result

    def read_export_data(self, rva: int, size: int) -> bytes | None:
        if self.export_rva <= rva < self.export_rva + self.export_size:
            return None
        offset = self.rva_offset(rva)
        if offset is None or offset + size > len(self.data):
            return None
        return self.data[offset : offset + size]


def guid_from_bytes_le(data: bytes) -> str:
    return str(uuid.UUID(bytes_le=data)).upper()


def default_guid_export_roots() -> list[Path]:
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    return [path for path in (system_root / "System32", system_root / "SysWOW64") if path.exists()]


def scan_guid_export_roots(labels: set[str], roots: Iterable[Path]) -> tuple[dict[str, GuidExport], dict[str, dict[str, list[str]]]]:
    if not labels:
        return {}, {}
    extensions = {".dll", ".exe", ".ocx", ".cpl", ".drv", ".ax"}
    candidates: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in root.iterdir():
            if path.suffix.lower() not in extensions:
                continue
            try:
                image = PEImage(path)
                exports = image.exports()
            except Exception:
                continue
            for label in labels & set(exports):
                data = image.read_export_data(exports[label], 16)
                if data is None:
                    continue
                candidates[label][guid_from_bytes_le(data)].append(str(path))

    resolved: dict[str, GuidExport] = {}
    conflicts: dict[str, dict[str, list[str]]] = {}
    for label, values in candidates.items():
        if len(values) == 1:
            guid, sources = next(iter(values.items()))
            resolved[label] = GuidExport(label, guid, sorted(sources))
        else:
            conflicts[label] = {guid: sorted(sources) for guid, sources in values.items()}
    return resolved, conflicts


def com_interfaces(model: Win32JsonModel) -> list[TypeDecl]:
    return [decl for decl in model.types if decl.kind == "Com"]


def interface_guid_value(model: Win32JsonModel, decl: TypeDecl) -> str | None:
    value = decl.item.get("Guid")
    if value:
        return value
    export = model.guid_exports.get(f"IID_{decl.emitted}")
    return export.guid if export else None


def expected_interface_iid_labels(model: Win32JsonModel) -> set[str]:
    return {f"IID_{decl.emitted}" for decl in com_interfaces(model) if interface_guid_value(model, decl)}


def uuid_iid_labels(model: Win32JsonModel) -> set[str]:
    return {
        model.uuid_symbol[index].emitted
        for index, _item in enumerate(model.uuid_constants)
        if model.uuid_symbol[index].emitted.startswith("IID_")
    }


def interface_guid_issues(model: Win32JsonModel) -> list[dict[str, str]]:
    interface_names = {decl.emitted for decl in com_interfaces(model)}
    issues: list[dict[str, str]] = []
    for decl in com_interfaces(model):
        if not decl.item.get("Guid"):
            label = f"IID_{decl.emitted}"
            export = model.guid_exports.get(label)
            if export:
                issues.append(
                    {
                        "issue": "resolved_from_export",
                        "api": decl.api,
                        "interface": decl.name,
                        "emitted_interface": decl.emitted,
                        "guid_label": label,
                        "guid": export.guid,
                        "source": ";".join(export.sources),
                    }
                )
                continue
            conflict = model.guid_export_conflicts.get(label)
            if conflict:
                issues.append(
                    {
                        "issue": "conflicting_export_guid",
                        "api": decl.api,
                        "interface": decl.name,
                        "emitted_interface": decl.emitted,
                        "guid_label": label,
                        "guid": ";".join(sorted(conflict)),
                        "source": ";".join(source for sources in conflict.values() for source in sources),
                    }
                )
                continue
            issues.append(
                {
                    "issue": "missing_guid",
                    "api": decl.api,
                    "interface": decl.name,
                    "emitted_interface": decl.emitted,
                    "guid_label": label,
                    "guid": "",
                    "source": "",
                }
            )
    for index, item in enumerate(model.uuid_constants):
        sym = model.uuid_symbol[index]
        if sym.emitted.startswith("IID_") and sym.emitted[4:] not in interface_names:
            issues.append(
                {
                    "issue": "missing_interface",
                    "api": item["_api"],
                    "interface": "",
                    "emitted_interface": "",
                    "guid_label": sym.emitted,
                    "guid": item["Value"],
                    "source": item["_api"],
                }
            )
    return issues


class Fasm2Writer:
    def __init__(self, model: Win32JsonModel, out_dir: Path):
        self.model = model
        self.out_dir = out_dir

    def write(self, clean: bool = False) -> None:
        if clean and self.out_dir.exists():
            resolved = self.out_dir.resolve()
            if resolved.name not in ARCH_TAGS:
                raise SystemExit(f"refusing to clean unexpected output directory: {resolved}")
            shutil.rmtree(resolved)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("equates", "types", "pcount", "imports", "data", "meta"):
            (self.out_dir / sub).mkdir(parents=True, exist_ok=True)

        self._write_root()
        self._write_equates()
        self._write_types()
        self._write_pcounts()
        self._write_imports()
        self._write_data()
        self._write_meta()

    def header(self, title: str) -> list[str]:
        return [
            f"; {title}",
            "; Generated from marlersoft/win32json. Do not edit by hand.",
            f"; Target architecture: {self.model.arch}",
        ]

    def _write_text(self, path: Path, lines: Iterable[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(lines).rstrip() + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")

    def _write_root(self) -> None:
        self._write_text(
            self.out_dir / "win32json.inc",
            [
                *self.header("win32json fasm2 declarations"),
                "include 'equates/all.inc'",
                "include 'types/all.inc'",
                "include 'pcount/all.inc'",
                "; Formatter-safe selective records are available below types/selective/.",
                "",
                "; Import tables are intentionally separate:",
                ";   include 'imports/library.inc'",
                ";   include 'imports/all.inc'",
                "; ApiSet import tables are opt-in:",
                ";   include 'imports/apisets_library.inc'",
                ";   include 'imports/apisets.inc'",
                "; Data-bearing UUID and PROPERTYKEY labels are separate too:",
                ";   include 'data/guids.inc'",
                ";   include 'data/propertykeys.inc'",
            ],
        )

    def _write_equates(self) -> None:
        lines = self.header("Constants and enum values")
        for index, item in enumerate(self.model.constants):
            sym = self.model.constant_symbol[index]
            value = item.get("Value")
            if value is None and item.get("ValueType") == "String":
                value = ""
            if isinstance(value, str):
                lines.append(f"?{sym.emitted} equ {fasm_value(value)}")
            else:
                lines.append(f"?{sym.emitted} = {fasm_value(value)}")

        lines.append("; enum values")
        for decl in self.model.types:
            if decl.kind != "Enum":
                continue
            base = decl.item.get("IntegerBase") or "UInt32"
            size, _align, _directive = NATIVE.get(base, NATIVE["UInt32"])
            lines.append(f"; enum {decl.name} ({base})")
            lines.append(f"sizeof.{decl.emitted} = {size}")
            for value_index, value in enumerate(decl.item.get("Values", []) or []):
                sym = self.model.enum_symbol[(decl.key, value["Name"], value_index)]
                lines.append(f"?{sym.emitted} = {fasm_value(value['Value'])}")

        self._write_text(self.out_dir / "equates" / "all.inc", lines)

    def _write_types(self) -> None:
        lines = self.header("Types")
        lines.extend(
            [
                "struct WIN32JSON_GUID",
                "Data1 dd ?",
                "Data2 dw ?",
                "Data3 dw ?",
                "Data4 db 8 dup (?)",
                "ends",
                f"WIN32JSON_PTR_SIZE = {self.model.ptr_size}",
            ]
        )

        for decl in self.model.ordered_types():
            if decl.kind in ("Struct", "Union"):
                lines.extend(self.render_record(decl))
            elif decl.kind == "NativeTypedef":
                layout = self.model.type_expr_layout(decl.item["Def"], decl)
                lines.append(f"; typedef {decl.name}")
                lines.append(f"sizeof.{decl.emitted} = {layout.size}")
            elif decl.kind == "FunctionPointer":
                params = len(decl.item.get("Params", []) or [])
                lines.append(f"; function pointer {decl.name}, params={params}")
                lines.append(f"sizeof.{decl.emitted} = {self.model.ptr_size}")
                lines.append(f"{decl.emitted}% = {params}")
            elif decl.kind == "Com":
                lines.extend(self.render_com(decl))
            elif decl.kind == "ComClassID":
                lines.append(f"; COM class id {decl.name}; bytes are in data/guids.inc")
                lines.append(f"sizeof.{decl.emitted} = {self.model.ptr_size}")
            elif decl.kind == "Enum":
                base = decl.item.get("IntegerBase") or "UInt32"
                size, _align, _directive = NATIVE.get(base, NATIVE["UInt32"])
                lines.append(f"; enum type {decl.name}; values are in equates/all.inc")
                lines.append(f"sizeof.{decl.emitted} = {size}")

        self._write_text(self.out_dir / "types" / "all.inc", lines)

        # Application-facing slices avoid colliding with formatter-owned
        # records when only a small set of API layouts is needed.
        for api, name in (("Networking.WinSock", "WSAData"),):
            decl = self.model.top_type_by_api_name[(api, name)]
            api_path = sanitize_identifier(api).lower()
            self._write_text(
                self.out_dir / "types" / "selective" / api_path / f"{decl.emitted}.inc",
                [
                    *self.header(f"Selective type: {api}.{name}"),
                    *self.render_record(decl),
                ],
            )

    def render_record(self, decl: TypeDecl) -> list[str]:
        record = self.model.record_layout(decl)
        lines = [
            f"; {decl.kind.lower()} {decl.name} ({decl.api}), sizeof={record.size}, align={record.align}",
            f"struct {decl.emitted}",
        ]
        if record.is_union:
            lines.append("union")
            for field in record.fields:
                lines.append(f"?{field.name} {field.render} ; {field.comment}")
            lines.append("ends")
            union_payload = max((field.size for field in record.fields), default=0)
            if record.size > union_payload:
                lines.append(f"db {record.size - union_payload} dup (?) ; tail padding")
        else:
            offset = 0
            pad_index = 0
            for field in record.fields:
                if field.offset > offset:
                    pad = field.offset - offset
                    lines.append(f"db {pad} dup (?) ; padding to offset {field.offset}")
                    pad_index += 1
                    offset = field.offset
                lines.append(f"?{field.name} {field.render} ; offset {field.offset}, {field.comment}")
                offset += field.size
            if record.size > offset:
                lines.append(f"db {record.size - offset} dup (?) ; tail padding")
        lines.append("ends")
        return lines

    def render_com(self, decl: TypeDecl) -> list[str]:
        methods = self.model.com_methods(decl)
        base_expr = decl.item.get("Interface")
        base = None
        if is_type_expr(base_expr):
            resolved = self.model.resolve_apiref(base_expr, decl)
            base = resolved.name if resolved else base_expr.get("Name")

        lines = [f"; interface {decl.name}" + (f" : {base}" if base else "")]
        if methods:
            lines.append(f"interface {decl.emitted},{','.join(methods)}")
        else:
            lines.append(f"sizeof.{decl.emitted} = {self.model.ptr_size}")
        return lines

    def _write_pcounts(self) -> None:
        dll_aliases = self.model.dll_aliases()
        by_dll: dict[str, list[tuple[str, int]]] = defaultdict(list)
        exact_by_name: dict[tuple[str, str], dict[str, Any]] = {}

        for index, item in enumerate(self.model.functions):
            label = self.model.function_symbol[index].emitted
            count = len(item.get("Params", []) or [])
            by_dll[item["DllImport"]].append((label, count))
            exact_by_name[(item["_api"], item["Name"])] = item

        all_lines = self.header("Parameter counts")
        include_files: list[str] = []
        for dll in sorted(by_dll, key=str.lower):
            alias = dll_aliases[dll]
            path = self.out_dir / "pcount" / f"{alias}.inc"
            include_files.append(f"pcount/{alias}.inc")
            lines = self.header(f"Parameter counts for {dll}")
            seen: set[str] = set()
            for label, count in sorted(by_dll[dll], key=lambda pair: pair[0].lower()):
                name = f"{label}%"
                if name not in seen:
                    lines.append(f"{name} = {count}")
                    seen.add(name)
            for api, aliases in sorted(self.model.unicode_aliases.items()):
                for stem in sorted(aliases):
                    fn = exact_by_name.get((api, f"{stem}W"))
                    if not fn or fn["DllImport"] != dll:
                        continue
                    name = f"{stem}%"
                    if name not in seen:
                        lines.append(f"{name} = {len(fn.get('Params', []) or [])}")
                        seen.add(name)
            self._write_text(path, lines)

        for inc in include_files:
            all_lines.append(f"include '{inc}'")
        self._write_text(self.out_dir / "pcount" / "all.inc", all_lines)

    def _write_imports(self) -> None:
        dll_aliases = self.model.dll_aliases()
        by_dll: dict[str, list[tuple[str, str]]] = defaultdict(list)
        exact_by_name: dict[tuple[str, str], tuple[dict[str, Any], str]] = {}

        for index, item in enumerate(self.model.functions):
            label = self.model.function_symbol[index].emitted
            by_dll[item["DllImport"]].append((label, item["Name"]))
            exact_by_name[(item["_api"], item["Name"])] = (item, label)

        dll_items = sorted(dll_aliases.items(), key=lambda pair: pair[0].lower())
        self._write_library(
            self.out_dir / "imports" / "library.inc",
            "PE concrete DLL import library declarations",
            [(dll, alias) for dll, alias in dll_items if not is_apiset_dll(dll)],
        )
        self._write_library(
            self.out_dir / "imports" / "apisets_library.inc",
            "PE ApiSet import library declarations",
            [(dll, alias) for dll, alias in dll_items if is_apiset_dll(dll)],
        )

        all_lines = self.header("PE import tables")
        apiset_lines = self.header("PE ApiSet import tables")
        include_files: list[str] = []
        apiset_include_files: list[str] = []
        for dll in sorted(by_dll, key=str.lower):
            alias = dll_aliases[dll]
            path = self.out_dir / "imports" / f"{alias}.inc"
            include_path = f"imports/{alias}.inc"
            if is_apiset_dll(dll):
                apiset_include_files.append(include_path)
            else:
                include_files.append(include_path)
            lines = self.header(f"Imports for {dll}")
            entries = sorted(by_dll[dll], key=lambda pair: pair[1].lower())
            if entries:
                lines.append(f"import {alias},\\")
                for index, (label, import_name) in enumerate(entries):
                    suffix = ",\\" if index + 1 < len(entries) else ""
                    lines.append(f"{label},{fasm_string(import_name)}{suffix}")

            alias_lines: list[str] = []
            for api, aliases in sorted(self.model.unicode_aliases.items()):
                for stem in sorted(aliases):
                    resolved = exact_by_name.get((api, f"{stem}W"))
                    if not resolved:
                        continue
                    item, label = resolved
                    if item["DllImport"] != dll:
                        continue
                    if label == f"{stem}W":
                        alias_lines.append(stem)
                    else:
                        size = "dword" if self.model.ptr_size == 4 else "qword"
                        lines.append(f"if used {stem}")
                        lines.append(f"label {stem}:{size} at {label}")
                        lines.append("end if")
            if alias_lines:
                lines.append("api \\")
                for index, stem in enumerate(alias_lines):
                    suffix = ",\\" if index + 1 < len(alias_lines) else ""
                    lines.append(f"{stem}{suffix}")
            self._write_text(path, lines)

        for inc in include_files:
            all_lines.append(f"include '{inc}'")
        self._write_text(self.out_dir / "imports" / "all.inc", all_lines)
        for inc in apiset_include_files:
            apiset_lines.append(f"include '{inc}'")
        self._write_text(self.out_dir / "imports" / "apisets.inc", apiset_lines)

    def _write_library(self, path: Path, title: str, dll_items: list[tuple[str, str]]) -> None:
        lines = self.header(title)
        if dll_items:
            lines.append("library \\")
            for index, (dll, alias) in enumerate(dll_items):
                suffix = ",\\" if index + 1 < len(dll_items) else ""
                lines.append(f"{alias},{fasm_string(dll)}{suffix}")
        self._write_text(path, lines)

    def _write_data(self) -> None:
        guid_lines = self.header("UUID data labels")
        for decl in self.model.types:
            if decl.kind == "Com":
                guid = interface_guid_value(self.model, decl)
                if guid:
                    guid_lines.append(f"IID_{decl.emitted} ddq {uuid_ddq(guid)}")
            elif decl.kind == "ComClassID" and decl.item.get("Guid"):
                guid_lines.append(f"CLSID_{decl.emitted} ddq {uuid_ddq(decl.item['Guid'])}")
        for index, item in enumerate(self.model.uuid_constants):
            sym = self.model.uuid_symbol[index]
            guid_lines.append(f"{sym.emitted} ddq {uuid_ddq(item['Value'])}")
        self._write_text(self.out_dir / "data" / "guids.inc", guid_lines)

        pkey_lines = self.header("PROPERTYKEY data labels")
        for index, item in enumerate(self.model.property_keys):
            sym = self.model.property_symbol[index]
            value = item["Value"]
            pkey_lines.append(f"{sym.emitted} ddq {uuid_ddq(value['Fmtid'])}")
            pkey_lines.append(f"dd {fasm_int(value['Pid'])}")
        self._write_text(self.out_dir / "data" / "propertykeys.inc", pkey_lines)

    def _write_meta(self) -> None:
        symbol_lines = ["raw_name\temitted_name\tkind\tapi\towner\treason"]
        for sym in sorted(self.model.symbols, key=lambda s: s.order):
            symbol_lines.append(
                f"{tsv_cell(sym.raw)}\t{tsv_cell(sym.emitted)}\t{sym.kind}\t{tsv_cell(sym.api)}\t{tsv_cell(sym.owner)}\t{tsv_cell(sym.reason)}"
            )
        self._write_text(self.out_dir / "meta" / "symbols.tsv", symbol_lines)

        guid_issues = interface_guid_issues(self.model)
        guid_lines = ["issue\tapi\tinterface\temitted_interface\tguid_label\tguid\tsource"]
        for issue in guid_issues:
            guid_lines.append(
                "\t".join(
                    tsv_cell(issue[key])
                    for key in ("issue", "api", "interface", "emitted_interface", "guid_label", "guid", "source")
                )
            )
        self._write_text(self.out_dir / "meta" / "interface_guids.tsv", guid_lines)

        interfaces = com_interfaces(self.model)
        missing_guid_count = sum(1 for issue in guid_issues if issue["issue"] == "missing_guid")
        resolved_export_count = sum(1 for issue in guid_issues if issue["issue"] == "resolved_from_export")
        conflicting_export_count = sum(1 for issue in guid_issues if issue["issue"] == "conflicting_export_guid")
        missing_interface_count = sum(1 for issue in guid_issues if issue["issue"] == "missing_interface")
        summary = {
            "arch": self.model.arch,
            "json_files": self.model.stats.json_files,
            "constants": self.model.stats.constants,
            "uuid_constants": self.model.stats.uuid_constants,
            "property_keys": self.model.stats.property_keys,
            "string_constants": self.model.stats.string_constants,
            "enum_values": self.model.stats.enum_values,
            "types": dict(self.model.stats.types),
            "functions": self.model.stats.functions,
            "unicode_aliases": self.model.stats.unicode_aliases,
            "flexible_arrays_treated_as_one": self.model.stats.flexible_arrays,
            "renamed_symbols": self.model.stats.renamed_symbols,
            "interface_guids": {
                "interfaces": len(interfaces),
                "with_guid": len(interfaces) - missing_guid_count,
                "from_metadata": sum(1 for decl in interfaces if decl.item.get("Guid")),
                "from_exports": resolved_export_count,
                "missing_guid": missing_guid_count,
                "conflicting_export_guid": conflicting_export_count,
                "iid_constants_without_interface": missing_interface_count,
            },
            "unresolved_refs": dict(self.model.stats.unresolved_refs),
        }
        (self.out_dir / "meta" / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def verify_generated(
    out_dir: Path,
    model: Win32JsonModel,
    fasm2: Path | None,
    fasm2_root: Path | None,
    fasm_timeout: int,
) -> int:
    errors: list[str] = []
    required = [
        out_dir / "win32json.inc",
        out_dir / "equates" / "all.inc",
        out_dir / "types" / "all.inc",
        out_dir / "types" / "selective" / "networking_winsock" / "WSAData.inc",
        out_dir / "pcount" / "all.inc",
        out_dir / "imports" / "library.inc",
        out_dir / "imports" / "all.inc",
        out_dir / "imports" / "apisets_library.inc",
        out_dir / "imports" / "apisets.inc",
        out_dir / "data" / "guids.inc",
        out_dir / "data" / "propertykeys.inc",
        out_dir / "meta" / "symbols.tsv",
        out_dir / "meta" / "interface_guids.tsv",
        out_dir / "meta" / "summary.json",
    ]
    for path in required:
        if not path.exists():
            errors.append(f"missing generated file: {path}")

    emitted = [sym.emitted for sym in model.symbols]
    duplicate_emitted = [name for name, count in Counter(emitted).items() if count > 1]
    if duplicate_emitted:
        errors.append(f"duplicate emitted symbols: {', '.join(sorted(duplicate_emitted)[:20])}")

    if model.stats.unresolved_refs:
        rendered = ", ".join(f"{key}={value}" for key, value in model.stats.unresolved_refs.most_common(20))
        errors.append(f"unresolved type references: {rendered}")

    summary_path = out_dir / "meta" / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("arch") != model.arch:
            errors.append(f"summary arch mismatch: {summary.get('arch')} != {model.arch}")

    guid_labels = data_labels(out_dir / "data" / "guids.inc")
    duplicate_guid_labels = [name for name, count in Counter(guid_labels).items() if count > 1]
    if duplicate_guid_labels:
        errors.append(f"duplicate GUID data labels: {', '.join(sorted(duplicate_guid_labels)[:20])}")
    guid_label_set = set(guid_labels)
    expected_iids = expected_interface_iid_labels(model)
    missing_iid_labels = sorted(expected_iids - guid_label_set)
    if missing_iid_labels:
        errors.append(f"missing interface GUID labels: {', '.join(missing_iid_labels[:20])}")
    unknown_iid_labels = sorted(
        label for label in guid_label_set if label.startswith("IID_") and label not in expected_iids | uuid_iid_labels(model)
    )
    if unknown_iid_labels:
        errors.append(f"IID labels without interface or UUID source: {', '.join(unknown_iid_labels[:20])}")

    dll_aliases = model.dll_aliases()
    apiset_aliases = {alias for dll, alias in dll_aliases.items() if is_apiset_dll(dll)}
    concrete_aliases = {alias for dll, alias in dll_aliases.items() if not is_apiset_dll(dll)}
    all_includes = import_include_aliases(out_dir / "imports" / "all.inc")
    apiset_includes = import_include_aliases(out_dir / "imports" / "apisets.inc")
    leaked_apisets = sorted(all_includes & apiset_aliases)
    if leaked_apisets:
        errors.append(f"imports/all.inc contains ApiSet includes: {', '.join(leaked_apisets[:20])}")
    leaked_concrete = sorted(apiset_includes & concrete_aliases)
    if leaked_concrete:
        errors.append(f"imports/apisets.inc contains concrete DLL includes: {', '.join(leaked_concrete[:20])}")

    if fasm2:
        errors.extend(run_fasm_smoke(out_dir, model, fasm2, fasm2_root, fasm_timeout))

    if errors:
        for error in errors:
            print(f"verify: {error}", file=sys.stderr)
        return 1

    report_interface_guid_issues(out_dir, model)
    print(f"verify: ok ({model.arch}, {out_dir})")
    return 0


def data_labels(path: Path) -> list[str]:
    labels: list[str] = []
    if not path.exists():
        return labels
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Za-z_?@$][A-Za-z0-9_?@$]*) ddq .+", line)
        if match:
            labels.append(match.group(1))
    return labels


def report_interface_guid_issues(out_dir: Path, model: Win32JsonModel) -> None:
    issues = interface_guid_issues(model)
    if not issues:
        return
    missing_guid_count = sum(1 for issue in issues if issue["issue"] == "missing_guid")
    resolved_export_count = sum(1 for issue in issues if issue["issue"] == "resolved_from_export")
    conflicting_export_count = sum(1 for issue in issues if issue["issue"] == "conflicting_export_guid")
    missing_interface_count = sum(1 for issue in issues if issue["issue"] == "missing_interface")
    parts: list[str] = []
    if missing_guid_count:
        parts.append(f"{missing_guid_count} interfaces missing GUIDs")
    if resolved_export_count:
        parts.append(f"{resolved_export_count} interface GUIDs resolved from exports")
    if conflicting_export_count:
        parts.append(f"{conflicting_export_count} interface GUID export conflicts")
    if missing_interface_count:
        parts.append(f"{missing_interface_count} IID UUID constants missing interfaces")
    print(f"verify: interface GUID report: {', '.join(parts)}; see {out_dir / 'meta' / 'interface_guids.tsv'}")


def import_include_aliases(path: Path) -> set[str]:
    aliases: set[str] = set()
    if not path.exists():
        return aliases
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"include 'imports/([^']+)\.inc'", line)
        if match:
            aliases.add(match.group(1))
    return aliases


def run_fasm_smoke(
    out_dir: Path,
    model: Win32JsonModel,
    fasm2: Path,
    fasm2_root: Path | None,
    timeout: int,
) -> list[str]:
    if not fasm2.exists():
        return [f"fasm2 executable not found: {fasm2}"]
    if fasm2_root is None:
        fasm2_root = fasm2.parent
    include_dir = fasm2_root / "include"
    if not include_dir.exists():
        return [f"fasm2 include directory not found: {include_dir}"]

    slash_out = out_dir.as_posix()
    errors: list[str] = []
    if model.arch in ("x86", "x64"):
        import_base = "win32a.inc" if model.arch == "x86" else "win64a.inc"
        import_format = "format PE console" if model.arch == "x86" else "format PE64 console"
        import_reg = "eax" if model.arch == "x86" else "rax"
        for title, apiset, library_inc, imports_inc in (
            ("concrete import", False, "library.inc", "all.inc"),
            ("ApiSet import", True, "apisets_library.inc", "apisets.inc"),
        ):
            label = first_import_label(model, apiset)
            if not label:
                continue
            import_smoke = "\n".join(
                [
                    f"include '{import_base}'",
                    import_format,
                    "entry start",
                    "section '.text' code readable executable",
                    "start:",
                    f"mov {import_reg},[{label}]",
                    "ret",
                    "section '.idata' import data readable writeable",
                    f"include '{slash_out}/imports/{library_inc}'",
                    f"include '{slash_out}/imports/{imports_inc}'",
                    "",
                ]
            )
            errors.extend(run_fasm_source(title, import_smoke, out_dir, include_dir, fasm2, timeout))

    if model.arch == "x86":
        com_inc = "macro/com32.inc"
    else:
        com_inc = "macro/com64.inc"
    smoke_lines = [
        "format binary",
        "include 'macro/struct.inc'",
        f"include '{com_inc}'",
        f"include '{slash_out}/win32json.inc'",
        "virtual at 0",
        "  smoke_guid WIN32JSON_GUID",
        "end virtual",
        "db 0",
    ]
    # Reference the last emitted constant and struct so silent mid-file parse
    # derailments (e.g. stray control bytes) fail the smoke instead of hiding.
    last_const = None
    for index, item in enumerate(model.constants):
        if isinstance(item.get("Value"), int) and not isinstance(item.get("Value"), bool):
            last_const = (model.constant_symbol[index].emitted, item["Value"])
    if last_const:
        smoke_lines.append(f"assert {last_const[0]} = {fasm_int(last_const[1])}")
    # Instantiate every struct/union: field-name collisions with struct macro
    # names only surface at instantiation time.
    smoke_lines.append("virtual at 0")
    for index, decl in enumerate(model.ordered_types()):
        if decl.kind in ("Struct", "Union"):
            smoke_lines.append(f"  smoke_{index} {decl.emitted}")
    smoke_lines.append("end virtual")
    smoke_lines.append("")
    errors.extend(run_fasm_source("declaration", "\n".join(smoke_lines), out_dir, include_dir, fasm2, timeout))
    return errors


def first_import_label(model: Win32JsonModel, apiset: bool) -> str | None:
    for index, item in enumerate(model.functions):
        if is_apiset_dll(item["DllImport"]) == apiset:
            return model.function_symbol[index].emitted
    return None


def run_fasm_source(
    title: str,
    source: str,
    out_dir: Path,
    include_dir: Path,
    fasm2: Path,
    timeout: int,
) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="win32json-fasm2-") as td:
        asm = Path(td) / "smoke.asm"
        bin_path = Path(td) / "smoke.bin"
        asm.write_text(source, encoding="utf-8", newline="\n")
        env = os.environ.copy()
        env["INCLUDE"] = f"{include_dir};{out_dir};{env.get('INCLUDE', '')}"
        command = [str(fasm2)]
        if fasm2.name.lower().startswith("fasmg"):
            command.append("-iInclude('fasm2.inc')")
        command.extend([str(asm), str(bin_path)])
        try:
            proc = subprocess.run(
                command,
                cwd=td,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return [f"fasm2 {title} smoke assembly timed out after {timeout} seconds"]
        if proc.returncode != 0:
            return [
                f"fasm2 {title} smoke assembly failed",
                proc.stdout.strip(),
                proc.stderr.strip(),
            ]
    return []


def build_model(args: argparse.Namespace) -> Win32JsonModel:
    api_dir = Path(args.api_dir).resolve()
    if not api_dir.exists():
        raise SystemExit(f"api directory not found: {api_dir}")
    model = Win32JsonModel(api_dir, args.arch)
    model.load()
    if not args.no_guid_export_scan:
        roots = [Path(path).resolve() for path in args.guid_export_root] if args.guid_export_root else default_guid_export_roots()
        model.load_guid_exports(roots)
    return model


def cmd_generate(args: argparse.Namespace) -> int:
    model = build_model(args)
    out_dir = Path(args.out_dir).resolve()
    Fasm2Writer(model, out_dir).write(clean=args.clean)
    print(f"generated {args.arch} include set at {out_dir}")
    if args.verify:
        fasm2 = Path(args.fasm2).resolve() if args.fasm2 else None
        fasm2_root = Path(args.fasm2_root).resolve() if args.fasm2_root else None
        return verify_generated(out_dir, model, fasm2, fasm2_root, args.fasm_timeout)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    model = build_model(args)
    out_dir = Path(args.out_dir).resolve()
    fasm2 = Path(args.fasm2).resolve() if args.fasm2 else None
    fasm2_root = Path(args.fasm2_root).resolve() if args.fasm2_root else None
    return verify_generated(out_dir, model, fasm2, fasm2_root, args.fasm_timeout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--api-dir", default="api", help="Directory containing win32json API files")
        p.add_argument("--arch", choices=sorted(ARCH_TAGS), default="x64")
        p.add_argument("--out-dir", default="generated/fasm2/x64")
        p.add_argument(
            "--guid-export-root",
            action="append",
            default=[],
            help="Directory of PE files to scan for exported IID_* GUID data; defaults to Windows System32/SysWOW64",
        )
        p.add_argument("--no-guid-export-scan", action="store_true", help="Do not supplement missing interface GUIDs from local PE exports")

    gen = sub.add_parser("generate", help="Generate fasm2 include files")
    add_common(gen)
    gen.add_argument("--clean", action="store_true", help="Remove the output directory first")
    gen.add_argument("--verify", action="store_true", help="Verify after generation")
    gen.add_argument("--fasm2", help="Path to fasmg/fasm2 executable for smoke assembly")
    gen.add_argument("--fasm2-root", help="Path to fasm2 checkout root containing include/")
    gen.add_argument("--fasm-timeout", type=int, default=300, help="Assembler smoke timeout in seconds")
    gen.set_defaults(func=cmd_generate)

    ver = sub.add_parser("verify", help="Verify generated include files")
    add_common(ver)
    ver.add_argument("--fasm2", help="Path to fasmg/fasm2 executable for smoke assembly")
    ver.add_argument("--fasm2-root", help="Path to fasm2 checkout root containing include/")
    ver.add_argument("--fasm-timeout", type=int, default=300, help="Assembler smoke timeout in seconds")
    ver.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    if args.out_dir == "generated/fasm2/x64" and args.arch != "x64":
        args.out_dir = f"generated/fasm2/{args.arch}"
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
