#!/usr/bin/env python3
"""Classify why a name collides with the fasm2/fasmg language layer.

For each candidate name, several tiny sources are assembled with fasm2
(struct.inc + com64.inc loaded, same environment the win32json projection
targets). Each context isolates one collision mechanism:

  predef       db (defined NAME)             does the include layer already
                                             define NAME as a symbol
                                             (register/element/constant)?
                                             A parse error here means NAME is
                                             an expression OPERATOR.
  def_plain    NAME = 0                      line-start interception by a
                                             directive, instruction, or macro.
  def_qpfx     ?NAME = 0                     does the `?` prefix bypass the
               assert NAME = 0               interception, and does a bare
                                             expression reference then work?
  use_expr     ?NAME = 5                     bare reference in expression
               probe = NAME + 1              context (catches operators and
                                             pre-existing elements).
  fld_plain    struct S / NAME db ? / ends   plain field definition,
               + instantiate + i.NAME        instantiation, dotted access.
  fld_qpfx     struct S / ?NAME db ? / ends  same with `?` prefix.
  fld_shadow   struct NAME / ends first,     field named like an existing
               then fld_plain                struct: the ends macro creates a
                                             line-start macro per struct name
                                             which hijacks the field line at
                                             instantiation time.
  fld_shadow_q same with `?` prefix on the field.

Verdict column summarises the minimal escape the projection needs:
  clean         no collision, emit as-is
  qpfx          `?` prefix on the definition suffices, name survives unchanged
  rename        bare references also break (operator / predefined symbol);
                only renaming helps
"""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

CONTEXTS = [
    "predef",
    "def_plain",
    "def_qpfx",
    "use_expr",
    "fld_plain",
    "fld_qpfx",
    "fld_shadow",
    "fld_shadow_q",
]

# Both full windows macro layers; a name is reported with its worst result
# across the two (proc64 defines e.g. `frame` that proc32 does not).
PRELUDES = {
    "w64": (
        "include 'macro/struct.inc'\ninclude 'macro/proc64.inc'\n"
        "include 'macro/com64.inc'\ninclude 'macro/import64.inc'\n"
        "include 'macro/export.inc'\ninclude 'macro/resource.inc'\n"
    ),
    "w32": (
        "include 'macro/struct.inc'\ninclude 'macro/proc32.inc'\n"
        "include 'macro/com32.inc'\ninclude 'macro/import32.inc'\n"
        "include 'macro/export.inc'\ninclude 'macro/resource.inc'\n"
    ),
}


def source_for(context: str, name: str, PRELUDE: str) -> str:
    if context == "predef":
        # `x = defined y` is rejected by the fasm2 assignment layer; the
        # if-form works. A parse error here marks NAME as an expression
        # operator (e.g. `string`).
        return PRELUDE + (
            f"probe = 0\nif defined {name}\nprobe = 1\nend if\ndb probe\n"
        )
    if context == "def_plain":
        return PRELUDE + f"{name} = 0\ndb 0\n"
    if context == "def_qpfx":
        return PRELUDE + f"?{name} = 0\nassert {name} = 0\ndb 0\n"
    if context == "use_expr":
        return PRELUDE + f"?{name} = 5\nprobe = {name} + 1\nassert probe = 6\ndb 0\n"
    # the trailing union exercises the union machinery (virtual at union)
    # inside the instance namespace, where e.g. a field label named `at`
    # poisons the addressing syntax
    field_body = (
        f"struct CTEST\n{{pfx}}{name} db ?\nunion\n?u1_ dw ?\n?u2_ dd ?\nends\nends\n"
        "virtual at 0\n  i CTEST\nend virtual\n"
        f"assert i.{name} = 0\nassert i.u2_ = 1\nassert sizeof CTEST = 5\ndb 0\n"
    )
    if context in ("fld_plain", "fld_qpfx"):
        pfx = "?" if context == "fld_qpfx" else ""
        return PRELUDE + field_body.format(pfx=pfx)
    if context in ("fld_shadow", "fld_shadow_q"):
        pfx = "?" if context == "fld_shadow_q" else ""
        return PRELUDE + f"struct {name}\npayload_ dd ?\nends\n" + field_body.format(pfx=pfx)
    raise ValueError(context)


def run_probe(fasmg: Path, include_dir: Path, asm: Path, out_bin: Path, timeout: int) -> tuple[str, str]:
    import os

    env = os.environ.copy()
    env["INCLUDE"] = str(include_dir)
    try:
        proc = subprocess.run(
            [str(fasmg), "-iInclude('fasm2.inc')", str(asm), str(out_bin)],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "HANG", "assembly did not terminate (resolver oscillation)"
    output = proc.stdout + proc.stderr
    if proc.returncode == 0 and "rror:" not in output:
        return "ok", ""
    detail = next(
        (line.strip() for line in output.splitlines() if "rror:" in line), "?"
    )
    # the trace line above the error names the intercepting macro/directive
    trace = ""
    lines = output.splitlines()
    for idx, line in enumerate(lines):
        if "rror:" in line and idx >= 2:
            trace = lines[idx - 2].strip()
            break
    return "FAIL", f"{detail} | {trace}"


def check_name(fasmg: Path, include_dir: Path, name: str, timeout: int) -> dict[str, tuple[str, str]]:
    import hashlib

    results: dict[str, tuple[str, str]] = {}
    # hash suffix: Windows filenames are case-insensitive, so DWord/Dword
    # would otherwise race on the same probe files across worker threads
    digest = hashlib.sha1(name.encode()).hexdigest()[:8]
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name) + "_" + digest
    rank = {"ok": 0, "sym": 1, "HANG": 2, "FAIL": 3}
    for context in CONTEXTS:
        worst = ("ok", "")
        for tag, prelude in PRELUDES.items():
            asm = OUT / f"{safe}.{context}.{tag}.asm"
            out_bin = OUT / f"{safe}.{context}.{tag}.bin"
            asm.write_text(source_for(context, name, prelude), encoding="ascii", newline="\n")
            status, detail = run_probe(fasmg, include_dir, asm, out_bin, timeout)
            if context == "predef" and status == "ok":
                value = out_bin.read_bytes()[:1]
                status = "sym" if value == b"\x01" else "ok"
            if rank[status] > rank[worst[0]]:
                worst = (status, detail)
        results[context] = worst
    return results


def verdict(res: dict[str, tuple[str, str]]) -> str:
    predef = res["predef"][0]
    if predef in ("FAIL", "sym"):
        return "rename"  # operator, or the include layer already owns the symbol
    if res["use_expr"][0] != "ok":
        return "rename"  # bare references break even after ?-definition
    if all(res[c][0] == "ok" for c in ("def_plain", "fld_plain")):
        return "clean"
    if all(res[c][0] == "ok" for c in ("def_qpfx", "fld_qpfx")):
        return "qpfx"
    return "rename"


def shadow_fix(res: dict[str, tuple[str, str]]) -> str:
    # fld_shadow fails for EVERY name (the ends macro hijacks any field named
    # like any existing struct); this column reports whether the `?` prefix
    # rescues such fields.
    if res["fld_shadow"][0] == "ok":
        return "n/a"
    return "qpfx" if res["fld_shadow_q"][0] == "ok" else "rename"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="names to test")
    parser.add_argument("--names-file", type=Path, help="one name per line")
    parser.add_argument("--fasm2-root", type=Path, default=Path(r"C:\git\fasm2"))
    parser.add_argument("--report", type=Path, default=HERE / "report.tsv")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--jobs", type=int, default=10)
    args = parser.parse_args()

    names = list(args.names)
    if args.names_file:
        names.extend(
            line.strip()
            for line in args.names_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
    if not names:
        parser.error("no names given")

    fasmg = args.fasm2_root / "fasmg.exe"
    include_dir = args.fasm2_root / "include"
    if not fasmg.exists():
        raise SystemExit(f"fasmg not found: {fasmg}")
    OUT.mkdir(exist_ok=True)

    rows: list[tuple[str, dict[str, tuple[str, str]]]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(check_name, fasmg, include_dir, name, args.timeout): name
            for name in names
        }
        for future in concurrent.futures.as_completed(futures):
            rows.append((futures[future], future.result()))
    rows.sort(key=lambda row: row[0].lower())

    lines = ["name\tverdict\tshadow_fix\t" + "\t".join(CONTEXTS) + "\tfirst_error"]
    for name, res in rows:
        first_error = next(
            (res[c][1] for c in CONTEXTS if res[c][0] == "FAIL"), ""
        )
        lines.append(
            f"{name}\t{verdict(res)}\t{shadow_fix(res)}\t"
            + "\t".join(res[c][0] for c in CONTEXTS)
            + f"\t{first_error}"
        )
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    counts: dict[str, int] = {}
    for name, res in rows:
        counts[verdict(res)] = counts.get(verdict(res), 0) + 1
    print(f"tested {len(rows)} names -> {args.report}")
    for kind in ("clean", "qpfx", "rename"):
        print(f"  {kind}: {counts.get(kind, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
