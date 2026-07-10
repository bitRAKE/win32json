#!/usr/bin/env python3
"""Collect collision suspects: every name the win32json projection emits that
also appears as a token anywhere in the fasm2 include tree (excluding the
stock Win32 equates/api/pcount data files, which are a coexistence question,
not a language-collision one). Only these names can possibly collide with the
fasm2/fasmg language layer; everything else is guaranteed inert."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOKEN = re.compile(r"[A-Za-z_?@$][A-Za-z0-9_?@$]*")
SKIP_DIRS = {"equates", "api", "pcount"}


def candidate_names(api_dir: Path) -> set[str]:
    names: set[str] = set()

    def walk_fields(item: dict) -> None:
        for field in item.get("Fields") or []:
            names.add(field["Name"])
        for nested in item.get("NestedTypes") or []:
            walk_fields(nested)

    for path in sorted(api_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for constant in data.get("Constants") or []:
            names.add(constant["Name"])
        for decl in data.get("Types") or []:
            names.add(decl["Name"])
            walk_fields(decl)
            for value in decl.get("Values") or []:
                names.add(value["Name"])
            for method in decl.get("Methods") or []:
                names.add(method["Name"])
        for function in data.get("Functions") or []:
            names.add(function["Name"])
    return names


def include_tokens(include_dir: Path) -> set[str]:
    tokens: set[str] = set()
    for path in include_dir.rglob("*.inc"):
        if SKIP_DIRS & {parent.name for parent in path.parents}:
            continue
        for match in TOKEN.finditer(path.read_text(encoding="latin-1")):
            tokens.add(match.group(0).rstrip("?").lower())
    return tokens


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-dir", type=Path, default=Path(__file__).resolve().parents[2] / "api")
    parser.add_argument("--fasm2-root", type=Path, default=Path(r"C:\git\fasm2"))
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "suspects.txt")
    args = parser.parse_args()

    names = candidate_names(args.api_dir)
    tokens = include_tokens(args.fasm2_root / "include")
    suspects = sorted(
        (name for name in names if name.rstrip("?").lower() in tokens),
        key=str.lower,
    )
    args.out.write_text("\n".join(suspects) + "\n", encoding="ascii")
    print(
        f"{len(names)} candidate names, {len(tokens)} include tokens,"
        f" {len(suspects)} suspects -> {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
