# fasm2 name-collision test

Answers: *why does a win32json name collide with the fasm2/fasmg language
layer, and what is the least-invasive escape?* Results drive the collision
handling in `scripts/win32json_fasm2.py` (`RENAME_EXACT`, `RENAME_CASELESS`,
`LINESTART_EXACT`, `LINESTART_CASELESS`, and the `?`-prefix emission).

## Usage

```
python harvest_suspects.py                 # -> suspects.txt (names worth probing)
python collision_test.py --names-file suspects.txt --report full_report.tsv
python collision_test.py Match Quality CY  # spot-check individual names
```

`harvest_suspects.py` intersects every name the projection emits (constants,
enum values, types, fields, methods, functions) with the identifier tokens of
the fasm2 include tree (minus the stock `equates/`, `api/`, `pcount/` data,
which is a *coexistence* question, not a language collision). Only ~1.5k of
~257k names can possibly collide; the rest are inert by construction.

`collision_test.py` assembles each name in eight contexts under BOTH windows
macro layers (win32 and win64) and reports the worst result. Probe sources
are left in `out/` for inspection.

## Collision mechanisms

1. **Line-start interception** (`def_plain` fails): fasmg recognizes
   directives, instructions, and macros in statement position, so
   `Match = 0Fh` invokes the `match` directive and `Add = 1` the `add`
   instruction. Case-insensitive for anything defined with the `name?`
   convention; case-SENSITIVE for plain macros (`Interface` is fine,
   `fScale` is not — x87 `fscale`).
   *Escape:* the fasmg `?` prefix (`?Match = 0Fh`) forces symbol
   interpretation. References never sit in statement position, so they work
   bare, including dotted access (`i.Match`). Verdict `qpfx`.

2. **Expression-level names** (`predef` = `sym`/`FAIL`, or `use_expr`
   fails): three sub-classes, none rescued by `?`:
   - *predefined elements* — registers and size words (`Eax`, `R8`, `cx`,
     `Byte`, `Word`) plus keyword-elements (`at`, `dup`, `from`, `scale`,
     `metadata`). Defining them — even `?`-prefixed — SILENTLY redefines the
     element; later instruction operands then misassemble. No error is ever
     raised, which is why these are the most dangerous class.
   - *operators* (`string`, case-insensitive): references misparse anywhere
     in an expression.
   - *circular symbolics* (`align`, `format`, `Float`, `end`): fasm2
     self-defines these (`define align? align?`), so touching them corrupts
     the language layer.
   *Escape:* rename with `_` postfix. Verdict `rename`.

3. **Struct-name shadowing** (`fld_shadow` fails for every name): fasm2's
   `ends` creates a line-start macro *per struct name* (for anonymous
   instantiation), so a field line `PrivateData dq ?` is hijacked as an
   instantiation of `struct PrivateData` when the containing struct is
   instantiated. This is why fields named `PrivateData`, `Quality`, `CY`
   collided — those are win32json's own struct names (Security.NAP,
   Media.DirectShow, System.Com) — while `CX` never did: no type is named
   CX. (`CX` is instead class-2: the register.)
   *Escape:* `?` prefix on the field (`shadow_fix` column).

4. **Namespace poisoning of struct machinery** (`fld_*` fail with the
   union-wrapped probe): a field label named `at` — even `?at` — lands in
   the instance namespace and breaks the union macro's own
   `virtual at union` statements. Caught only because the field probes wrap
   the field together with a union.

## Reading the report

- `verdict`: `clean` (emit as-is) / `qpfx` (`?` prefix suffices, name
  preserved) / `rename` (`_` postfix required).
- `shadow_fix`: whether `?` rescues a field whose name matches an existing
  struct (mechanism 3) — `fld_shadow` itself fails for every name by
  construction.
- `predef` = `sym` marks names the include layer already defines
  (mechanism 2, silent-clobber class).
- `HANG` means fasmg did not terminate (resolver oscillation) — treated as
  failure.

## Regenerating after fasm2 include changes

The verdicts are only as current as the fasm2 include tree they were probed
against (`--fasm2-root`, default `C:\git\fasm2`). Re-run both scripts after
updating fasm2 and diff `full_report.tsv`; feed any class changes back into
the lists in `scripts/win32json_fasm2.py`.
