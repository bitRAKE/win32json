# Curated fasmg/x86-2 implementation base

The consolidated Win32 projection is a new implementation built on fasmg and
x86-2, not another compatibility layer over the complete fasm2 include tree.
Every additional include must justify both its behavior and its ownership of
special macro/CALM names.

## Two-phase source model

Formatting must be selected before the project installs its generated type and
call layers.  The intended public shape is:

```asm
include 'win32/core.g'         ; data, alignment, format dispatch, x86-2
format MS64 COFF               ; or: format PE64 console
include 'win32/windows.g'      ; structs, contracts, backend, COM/UUID support
```

`core.g` should not choose an output format.  `windows.g` may inspect the
already-selected backend identity, but must not silently change it.

## Accepted foundation

The initial x64 baseline is equivalent to:

```asm
include 'dd.inc'
include 'align.inc'
include 'format.inc'
include 'x86-2.inc'
use AMD64                       ; or `use everything` during bring-up

; user selects format here

include 'macro/struct.inc'
```

Responsibilities:

- fasmg core: symbolic assembly, namespaces, macros, CALM, virtual blocks;
- `dd.inc`: x86 data directives with formatter-overridable emitters;
- `align.inc`: relocation-aware alignment;
- `format.inc`: explicit PE/COFF formatter selection;
- `x86-2.inc`: operand parsing and instruction encoding (and `xcalm.inc`);
- `macro/struct.inc`: generated record instantiation after format selection.

`use AMD64` is the preferred baseline policy. `use everything` is useful while
bringing up metadata coverage. Either is an x86 feature-selection policy, not
permission to import the whole fasm2 language surface. x86-2 still defines its
complete mnemonic database; the `use` selection controls what a source may
assemble rather than removing definitions.

The order matters.  The COFF/PE format modules use private structure helpers
while initializing themselves; the project structure layer is installed only
after the `format` statement.

## Deliberately excluded

Do not include aggregate `fasm2.inc`.  It currently pulls in helpers that are
not part of this language:

```text
@@.inc
times.inc
irps.inc
fix.inc
```

Also exclude:

- `macro/proc64.inc` and `macro/proc32.inc`;
- legacy `invoke`, `cinvoke`, `stdcall`, and `addr` syntax;
- `macro/com64.inc` / `macro/com32.inc`;
- legacy import-table macros and `win64*.inc` / `win32*.inc` umbrellas;
- TCHAR and implicit A/W coercion;
- flat SDK equate/pcount include sets when generated typed contracts exist.

Invoke `fasmg.exe` directly for this implementation. The stock `fasm2.cmd`
injects `fasm2.inc` before the source and would silently reinstall the excluded
language layers.

The projection uses direct first-class function instructions and `&value` for
an address-valued argument.  A raw `lea`, manual register setup, and `call`
remain available when bypassing the projection.  No compatibility alias for
`addr` or `invoke` is provided.

Native fasmg `repeat`, `iterate`, and `irp` remain language primitives.
Excluding `times.inc` only removes the compatibility surface named `times`.
Similarly, excluding `fix.inc` prevents global token-rewrite rules; it does not
remove ordinary symbolic definitions.

## Project-owned layers

After format selection, `windows.g` installs only the selected implementation:

1. generated structures, typedef identities, and typed value namespaces;
2. the parameter pre-scan/register-retirement scheduler;
3. size-oriented Win64 assignment lowering;
4. `win32.fastcall` PE/COFF/COM target resolution;
5. `interface?`, exact COM method contracts, and storage tags;
6. the assemble-time UUID database and backend data materializer;
7. the selected PE import collector or COFF external-symbol adapter.

The call scheduler replaces `proc64.inc`'s fastcall/invoke family.  The format
backend replaces legacy import macros.  `scripts/combase.g` and
`scripts/fastcall.g` are current prototypes of two small pieces, not reasons to
pull their historical umbrella includes back into the implementation.

The scheduler's normalized job model, physical-register dependency rules, and
cycle fallback are specified in [`CALL_SCHEDULER.md`](CALL_SCHEDULER.md).

## Interceptor ownership

Special names are a limited resource in fasmg:

- x86-2 temporarily uses root `?` while declaring settings, then purges it;
- x86-2 retains root `??` for instruction fallback and annotated settings;
- `format.inc` owns `format?` and the selected formatter owns section/output
  directives;
- `macro/struct.inc` owns `struct?`, `union?`, and their block machinery;
- the Win32 layer owns `interface?`, generated API instructions, and object
  instance CALM instructions.

`fix.inc` is particularly incompatible with this ownership model because its
activated form installs a root `?!` transformer. `macro/inline.inc`,
`macro/if.inc`, and parameterized `win64*x.inc` roots are excluded for the same
reason. `macro/struct.inc` uses the root collector slots only while reading a
structure block and restores them at `ends`.

The Win32 implementation must not install another catch-all `?`/`??` handler.
Generated function names are explicit CALM instructions.  This keeps include
order auditable and prevents unrelated language additions from changing how a
line is parsed.

## Acceptance fixture

`tests/fasm2-calm/minimal_base.asm` assembles Microsoft x64 COFF without
`fasm2.inc` and verifies that `fix`, `times`, `invoke`, and `addr` remain
ordinary available symbols.  That fixture is the initial dependency budget:
adding another include requires a focused use case and an interceptor/collision
audit.

The stock `macro/import64.inc` is separable and can be used as a temporary PE
backend experiment, but it is not part of the target baseline because the
projection intends to materialize only imports proven used by generated API
contracts.
