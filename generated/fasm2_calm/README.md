# Consolidated fasm2/CALM projection

This directory is the design root for a generated Win32 projection that uses
the complete win32json contract instead of exposing independent tables of
equates, parameter counts, imports, and types.  The public surface should be
the same whether the consuming source assembles a PE executable directly or
produces a Microsoft COFF object for a linker.

The first acceptance case is `CreateProcessW`:

```asm
CreateProcessW ,,,,win32.BOOL.FALSE,\
        win32.PROCESS_CREATION_FLAGS.CREATE_NEW_CONSOLE,,,&.si,&.pi
```

The omitted optional arguments become zero.  Required arguments are still
required, and the call lowering is selected by the output backend.

The preferred application surface is a single format-aware include:

```asm
format PE64 NX console 6.0
define win32.select.downlevel kernel32
include 'generated/fasm2_calm/x64/windows.inc'
```

`windows.inc` chooses PE, legacy Microsoft COFF, or NEWCOFF linkage from
definite formatter state and postpones direct-PE import output. Files below
`contracts/` and `backends/` are implementation and focused-test seams.

This file records the abstractions that must be stable before generating the
full API.  Syntax shown for generated contracts is intended syntax.  Backend
configuration names are provisional until the PE and COFF prototypes have
both assembled successfully.

The curated fasmg/x86-2 include foundation and deliberate language exclusions
are specified in [`IMPLEMENTATION_BASE.md`](IMPLEMENTATION_BASE.md).
Floating literal, source-representation, and ABI-lane rules are specified in
[`FLOAT_ARGUMENTS.md`](FLOAT_ARGUMENTS.md).
The generated and tested x64 function/value/linkage surface is described in
[`IMPLEMENTED_X64.md`](IMPLEMENTED_X64.md).

## Projection layers

The projection has four layers.  Keeping them separate is what permits one
function macro to work in both output modes.

1. **Metadata model** - resolved types, layouts, symbol collisions, DLL
   ownership, architecture filters, COM inheritance, UUIDs, and parameter
   attributes.  The existing `scripts/win32json_fasm2.py` model already
   supplies most of this layer.
2. **Contract declarations** - generated value namespaces, function
   calminstructions, interface/method contracts, type declarations, and the
   assemble-time UUID database.  These declarations do not create imports,
   external symbols, sections, or constant data merely by being included.
3. **Lowering services** - architecture-specific argument placement and call
   generation.  A contract delegates to this layer after applying defaults
   and the safe value transformations described below.
4. **Output backend** - records used functions and UUIDs, then materializes
   PE imports/data or COFF externals/data and relocations.

The contract layer may depend on the lowering and backend protocols.  It must
not depend on a specific PE or COFF implementation.

## Function contracts

Each function becomes a CALM instruction whose formal parameters mirror the
Win32 signature.  `Optional` parameters receive a zero default; all others
use the required-parameter form.  For example, metadata for `CreateProcessW`
projects to:

```asm
calminstruction CreateProcessW \
        lpApplicationName:0,lpCommandLine:0,\
        lpProcessAttributes:0,lpThreadAttributes:0,\
        bInheritHandles*,dwCreationFlags*,\
        lpEnvironment:0,lpCurrentDirectory:0,\
        lpStartupInfo*,lpProcessInformation*

        transform bInheritHandles,win32__BOOL
        transform dwCreationFlags,win32__PROCESS_CREATION_FLAGS

        local target,arguments
        initsym target,CreateProcessW
        arrange arguments,\
                lpApplicationName,lpCommandLine,\
                lpProcessAttributes,lpThreadAttributes,\
                bInheritHandles,dwCreationFlags,\
                lpEnvironment,lpCurrentDirectory,\
                lpStartupInfo,lpProcessInformation
        call win32.fastcall,target,arguments
end calminstruction
```

`scripts/fastcall.g` currently supplies a transitional backend-neutral CALM
adapter for the focused routing fixture. CALM's `call` command receives the
complete operands as one arranged symbolic value. The adapter transforms a
normal function identity through `win32.linkage`, while a `{vtable-offset}`
target bypasses linkage lookup. Its wrapped historical macro is not the
production lowering path because it emits destructively from left to right.
The replacement retains the `win32.fastcall` entry point and sends the intact
list through the scheduler before encoding assignments.

The generated contract retains the following facts even when they do not
immediately change emitted instructions:

- DLL and entry-point name;
- return type and return attributes;
- parameter name, order, type, and `In`, `Out`, `Optional`, and `Const`
  attributes;
- architecture and minimum-platform constraints;
- `SetLastError` behavior;
- calling convention when supplied by metadata.

`SetLastError` is descriptive.  A normal call must not implicitly read or
clear the last-error value.  Platform constraints should initially be
available to diagnostics and generated contract reports; they should not
silently reject assembly unless a target platform was explicitly selected.

### Value transformation policy

The default projection stays permissive enough to accept immediates,
registers, addresses, and memory operands.  Validation is intentionally
asymmetric:

- Public Boolean and enum/flags values use names such as
  `win32.BOOL.FALSE` and `win32.IUIAutomation.TreeScope.DESCENDANTS`.
- Generated method/function contracts use a flat internal resolver for terse
  symbolic operands.  For example, `win32__BOOL.FALSE` aliases the public
  value and is the namespace passed to CALM `transform`.  This avoids fragile
  deep namespace rebinding while keeping the public symbol space vertical.
- A failed transform leaves the original operand intact.
- Registers deliberately bypass symbolic and storage-tag checks.  Supplying a
  register means the caller owns its type and value correctness.
- Raw numeric expressions remain valid and do not need a typed spelling.
- Relocatable memory symbols may carry an assemble-time-only
  `__win32_type` tag.  An optional checker may diagnose a mismatch only when
  both the expected type and the storage tag are definite.
- Untagged memory, compound address expressions, and pointer values loaded
  through registers remain unchecked.
- Direction and constness are retained as contract metadata, not enforced by
  the baseline call macro.
- A narrow scalar contract defines only its low value bits in the 64-bit ABI
  register/slot. Lowering may use a wider destination operation when smaller,
  but may not widen a memory-source read beyond the definite object width.
- A `Single`/`Double` contract selects scalar FP placement independently of
  whether the supplied source parses as an immediate, GPR, XMM, or memory.
  Floating numeric values remain unsized until that contract or an explicit
  operand/instruction requests binary32 or binary64 emission.

No check may add runtime loads, copies, or temporaries.  After assemble-time
resolution, the original operand list is handed to `win32.fastcall`.  Deeper
pointer dataflow would be an academic type system without a backend optimizer
capable of removing the resulting conservatism, so it is outside the baseline
projection.

## Symbol spaces

The canonical projection is vertical:

```text
win32.BOOL.FALSE
win32.BOOL.TRUE
win32.PROCESS_CREATION_FLAGS.CREATE_NEW_CONSOLE
win32.VARENUM.VT_BSTR
win32.IUIAutomation.TreeScope.DESCENDANTS
win32.IUIAutomation.UIA_AUTOMATION_ID_PROPERTY_ID
win32.UUID.IID_IUnknown
```

Types and values belong to their type namespace.  Aliases can refer to a
canonical value without creating another data object.  An interface namespace
may expose constants and enum aliases relevant to its methods; shared values
still have one canonical API/type identity.

Functions need both an unambiguous canonical identity and a terse spelling.
The generator should retain a canonical DLL-qualified identity such as
`win32.api.kernel32.CreateProcessW`, then expose `CreateProcessW` when the
name is unique.  A duplicate function name must not be resolved by load order;
only its qualified form is safe.  The existing collision report remains the
source for fasmg parser-name exceptions.

COM interface names remain first-class type/macros so declarations such as
`IUIAutomation` and member calls such as `.pAutomation->ElementFromHandle`
stay compact.  Their UUID values live in the UUID namespace/data system, not
inside the interface macro itself.

## Call lowering protocol

Parameter ordering and cycle handling are specified in
[`CALL_SCHEDULER.md`](CALL_SCHEDULER.md). The size-oriented Win64 lowering
policy and its permitted CPU-state side effects are specified separately in
[`ABI_OPTIMIZATION.md`](ABI_OPTIMIZATION.md). Scheduling is authoritative:
the optimizer receives already ordered assignments and may not reorder across
unretired source dependencies.

The function contract delegates one normalized request containing:

```text
function identity + ordered operands + architecture + selected backend
```

The lowering service is responsible for ABI details: register assignment,
stack arguments, shadow space, stack alignment, volatile scratch selection,
and result register convention.  This division is important even on x64:
`CreateProcessW` has ten parameters, so the acceptance test exercises both
register and stack arguments.

The CALM contract layer does not generate another call sequence. It resolves
defaults and symbolic values, then delegates the unchanged operands to
`win32.fastcall`. That service pre-scans and schedules them as one bounded
parallel assignment. COM dispatch still emits exactly one object load and one
vtable-slot call; abstraction depth affects assembly work, not runtime
indirection.

The backend must be selected explicitly before the projection is used.
Inferring the mode from incidental formatter symbols is fragile and prevents
clear diagnostics.  Including a second, conflicting backend is an error.

### Direct PE/EXE backend

For direct executable assembly the backend:

- records each referenced DLL/function pair;
- lowers the call through the corresponding import-address-table entry;
- emits one consolidated import directory for used functions;
- groups imports deterministically by DLL and entry-point identity;
- materializes used UUID/property-key data in an aligned read-only area;
- supplies backend hooks for section placement instead of forcing a complete
  executable layout on the caller.

The include must not import the entire Win32 surface.  Merely declaring a
function is side-effect free; using it marks its import identity for delayed
emission.

### Microsoft COFF backend

For object creation the backend:

- declares or records only referenced external function symbols;
- uses the architecture-correct COFF symbol spelling and relocation form;
- emits calls suitable for resolution through the linker's import library;
- does not emit a PE import directory or DLL library table;
- materializes used constant data with internal linkage by default;
- permits an explicit public-data mode when one canonical definition is
  intentionally shared across objects.

The COFF backend must not own the final executable's section layout.  It may
select conventional `.text`, `.rdata`, and directive sections for artifacts
it creates, while allowing the surrounding object source to choose where its
code and ordinary data reside.

On x86, stdcall decoration and byte counts are backend/ABI facts.  On x64 and
ARM64, symbol spelling and relocation differ even though no stdcall suffix is
used.  Therefore the old generated `%` parameter-count equates are an input
to legacy x86 lowering, not part of the new public interface.

## COM interface projection

The working `interface?` macro in `scripts/combase.g` is the kernel for the
member-call surface.  It already provides all three useful access levels:

- `IFACE__Method` vtable-offset labels for manual calls;
- `IFACE__Method object,args...` method CALM instructions;
- an `IFACE` object struc supporting `object->Method args...`.

It also carries inherited method lists in `win32.COM`, creates an interface
method list for object output, opens `win32.IFACE` for interface-local values,
tags object storage with `__win32_type`, and connects a used `IID_IFACE` label
to the GUID database.  Generation should feed this kernel resolved contracts
rather than flattening an interface to method names as the current fasm2
writer does.  The public projection should preserve these three access levels.

For every interface, preserve:

- canonical interface identity and IID identity;
- base interface and inherited vtable slots;
- final slot index for every method;
- method return type and ordered parameter contracts;
- overload identity while retaining a usable source spelling;
- architecture/platform constraints.

The `object->Method ...` expansion adds the object pointer as the implicit
first ABI argument and performs an indirect vtable call.  It uses the same
architecture lowering service as functions, but it does not ask either
backend for an external function symbol.  Calls used to obtain the object,
such as `CoCreateInstance`, remain ordinary backend-mediated API calls.

`interface?` emits an object-plus-rest fallback so incomplete metadata remains
usable.  The generator then replaces each fallback with an exact method
contract.  A representative specialization is:

```asm
calminstruction IUIAutomationElement__FindFirst object*,scope*,condition*,found*
        local target,arguments
        initsym target,{IUIAutomationElement__FindFirst}
        transform scope,win32__IUIAutomationElement__TreeScope
        arrange arguments,object,scope,condition,found
        call win32.fastcall,target,arguments
end calminstruction
```

The generated flat resolver is an implementation detail.  Callers may use a
fully qualified interface value, a recognized short symbol such as
`DESCENDANTS`, a raw number, memory, or a register.

The remaining backend-sensitive integration points are:

- `{const:16} IID_IFACE GUID iid`, so used IID data is placed by the selected
  backend;
- output consumption of the backend-neutral `win32.COM.IFACE` registry;
- optional storage-tag diagnostics and inherited-interface compatibility.

Generation must diagnose an unresolved base interface, duplicate/ambiguous
method identity, or a missing slot.  A missing IID is a data-availability
diagnostic and need not prevent use of an already-obtained interface pointer.

## UUID database and data materialization

`scripts/uuid.inc` demonstrates the intended two-space design:

1. an assemble-time namespace maps names and aliases to UUID values;
2. a delayed data space emits aligned 16-byte constants only for referenced
   UUID names.

The consolidated projection should incorporate that design with these rules:

- normalize standard text, C initializer, and symbolic/alias forms to one
  128-bit value;
- preserve little-endian GUID field encoding in emitted bytes;
- resolve aliases to a canonical value before deciding whether data is used;
- guarantee at least four-byte alignment (optionally sixteen when the backend
  can do so without padding surprises);
- let the backend choose the data section and linkage;
- diagnose conflicting values for the same canonical name;
- make repeated references idempotent.

The current UUID and COM prototypes are deliberately not copied into this
generated tree: they are untracked working material and should be integrated
only after namespace ownership and backend emission hooks are settled.

## Proposed generated layout

```text
generated/fasm2_calm/
  README.md                 this design and projection contract
  x86/
    windows.g               public include
    contracts/              functions and COM methods
    types/                  records, typedefs, interfaces
    values/                 typed enum/constant namespaces
    uuid/                   assemble-time UUID database
    backends/               PE and COFF adapters
    meta/                   diagnostics and contract reports
  x64/
    ...
  arm64/
    ...
```

`windows.g` should include declaration-only components and the common lowering
protocol.  A backend-specific include should be explicit and small.  Generated
files should remain deterministic and carry a do-not-edit header; this README
is the hand-maintained exception.

## Questions to settle with prototypes

The architecture above deliberately leaves a small set of implementation
choices open until they can be answered by assembled output:

- Whether one final `postpone` collector is sufficient for calls and data
  referenced through aliases, or whether each declaration must register use
  eagerly with the selected backend.
- The exact external-symbol and relocation declarations accepted by the fasm2
  COFF formatter on x86, x64, and ARM64, including import-library decoration.
- How backend-owned generated sections compose with a source that already has
  `.rdata`, `.idata`, or directive sections.
- Whether UUID data should default to one private copy per COFF object or use
  COMDAT-like deduplication when the formatter and linker support it reliably.
- How ApiSet DLL identities map to import libraries in COFF mode and to host
  DLL/import descriptors in direct PE mode.
- Whether A/W Unicode aliases should be opt-in source aliases or remain only
  explicit metadata contracts; implicit aliases can hide string-width errors.
- How overloaded COM methods retain a stable metadata identity while the
  source-level name and inherited vtable slot remain natural.
- Which namespace owns the special line interceptors used by `interface?`,
  object strucs, and generated function instructions when other macro suites
  are included.
- Whether interface-local aliases should include every value used by a method
  or only values whose ownership is unambiguous in metadata.

Each question should be decided by a small PE/COFF fixture and an external
symbol, relocation, byte, or import-table assertion—not only by successful
assembly.

## Generator work sequence

1. Extend the model with a reusable rendered type identity for parameters,
   returns, fields, and COM methods.  Do not reduce a type to storage size.
2. Generate typed value namespaces, including `BOOL.TRUE/FALSE` locally and
   enum/flags values beneath their enum type.
3. Generate `CreateProcessW` and a small mixed contract set (`ExitProcess`,
   `CoInitialize`, `CoCreateInstance`, and `FindWindowA`) against a recording
   backend.  Verify defaults, required arguments, and the ten-argument ABI.
4. Connect the direct PE backend and verify its import directory and UUID
   bytes externally.
5. Connect the COFF backend, inspect symbols/relocations, and link the object
   with the appropriate Windows import libraries.
6. Expand the focused `interface?` contract fixture to inherited IUnknown
   methods plus a multi-level interface such as `IUIAutomation`.
7. Generate the complete API only after collision, duplicate identity, and
   delayed-emission tests pass for the focused set.

## Focused acceptance checks

The first executable and object tests should prove the same source-level call
contract in both modes:

- `CreateProcessW` accepts omitted optional positions as zero;
- omitting any of the four required arguments is rejected;
- `win32.BOOL.FALSE` resolves without a global `FALSE` symbol;
- typed and raw creation-flag operands both assemble;
- all ten operands reach their ABI locations;
- a two-GPR value swap emits one `xchg`, and a longer pure permutation emits
  exactly one fewer `xchg` than registers in the cycle;
- BYTE/WORD values may use smaller promoted encodings while narrow memory
  sources are never over-read;
- PE output contains one used `KERNEL32.dll` import and no unused imports;
- COFF output contains the expected external symbol/relocation and no PE
  import directory;
- UUID aliases produce one correctly encoded constant per output unit;
- an inherited COM method receives the implicit object pointer and correct
  vtable slot;
- exact and `object->Method` forms produce the same instructions;
- a register operand bypasses symbolic/type checking;
- interface pointer storage tags occupy no bytes and add no instructions.

These checks define the boundary between the metadata projection and the two
output mechanisms.  Once they pass, expanding from the focused set to the
full win32json database is primarily deterministic generation rather than
new macro-language design.
