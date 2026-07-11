# Implemented x64 unified projection

The generated x64 function/value/linkage surface lives under `x64/` and is
produced by `scripts/win32json_fasm2_calm.py`.

```powershell
python scripts\win32json_fasm2_calm.py generate `
  --api-dir api --arch x64 `
  --out-dir generated\fasm2_calm\x64 --clean
```

The current metadata produces:

```text
17,083 total x64 function contracts
16,823 concrete/down-level DLL contracts
   260 API-set contracts
17,081 collision-safe raw aliases
```

Every function always has a canonical DLL-qualified spelling:

```asm
win32.api.kernel32.CreateProcessW ...
win32.api.dsound.GetDeviceID ...
win32.api.tbs.GetDeviceID ...
```

Canonical contracts retain parameter names, order, optional defaults,
direction/const comments, return type, `SetLastError`, DLL identity, and enum or
Boolean transforms. Public raw aliases are thin CALM calls into the canonical
contract, so validation and target resolution exist in one place.

## Preferred unified include

Consumers select the required libraries and include `windows.inc` once after
choosing an output format:

```asm
format PE64 NX console 6.0
define win32.select.downlevel kernel32,ws2_32
include 'generated/fasm2_calm/x64/windows.inc'
```

or:

```asm
format MS64 COFF
define win32.select.apisets api_ms_win_core_winrt_l1_1_0
include 'generated/fasm2_calm/x64/windows.inc'
```

The facade installs the common runtime/value surface, qualified contracts, raw
public aliases, and linkage definitions for each selected library. It accepts:

- definite `PE.Settings.Machine` for direct PE;
- definite `COFF.Settings.Machine` for legacy Microsoft COFF;
- definite `NEWCOFF.RELOC_REL32` with 64-bit x86 mode for NEWCOFF, whose
  machine is intentionally finalized by its own `postpone`.

All three routes reject a non-AMD64 configuration. NEWCOFF uses the same
external-symbol linkage contracts as legacy COFF while retaining its bigobj
record, CodeView, COMDAT, and unwind materializers.

For direct PE, `postpone` creates `.idata` and invokes the used-only import
materializer after all calls are known. COFF library files already postpone
their used `extrn` declarations. Selecting both down-level and API-set families
in one direct PE remains an explicit error until their descriptor lists have a
combined materializer.

The individual `windows.g`, `contracts/`, and `backends/` files remain focused
test and unusual-composition seams; they are not the normal application include
surface.

## Function-set gates

Choose at most one flat public function set:

```asm
include 'windows_downlevel.g' ; concrete DLL exports, default compatibility path
; or
include 'windows_apisets.g'   ; API-set contracts
```

Including both is a deliberate assembly error. Code that needs both identity
spaces without global names uses:

```asm
include 'windows_qualified.g'
```

The x64 metadata currently contains one true function/function collision:

```text
GetDeviceID -> DSOUND.dll (2 parameters)
GetDeviceID -> tbs.dll    (4 parameters)
```

Neither receives an automatic raw alias. Select one explicitly when desired:

```asm
include 'contracts/downlevel/collisions/GetDeviceID_dsound.g'
; or
include 'contracts/downlevel/collisions/GetDeviceID_tbs.g'
```

Both qualified contracts remain available simultaneously. The generated
`meta/function_collisions.tsv` report records every withheld raw alias and its
reason.

## Values

`windows.g` installs vertical enum, Boolean, and constant namespaces without
global `TRUE`, `FALSE`, or enum-value pollution:

```asm
win32.BOOL.FALSE
win32.PROCESS_CREATION_FLAGS.CREATE_NEW_CONSOLE
win32.constant.Foundation.MAX_PATH
```

The `win32` root and each enum namespace are anchored with circular definitions
(for example, `define win32 win32` and `define win32.BOOL win32.BOOL`).
Generated CALM contracts transform against that same public namespace,
allowing the terse short spelling when the formal parameter identifies the
enum:

```asm
CreateProcessW ,,,,FALSE,CREATE_NEW_CONSOLE,,,0,0
```

Metadata occasionally exposes a semantically richer parameter as a plain
integer. Small reviewed overrides may add a resolver without restricting the
accepted operand domain. `ExitProcess`, for example, still accepts any UInt32
but also resolves known status names through `win32.WIN32_ERROR`:

```asm
ExitProcess ERROR_SUCCESS
```

## Selective types

Type layouts are separately includable so a consumer does not need to install
thousands of unrelated structure names. The initial generated slice is:

```asm
include 'types/networking_winsock/WSAData.g'

sub rsp,32 + sizeof WSAData
```

The definition is rendered from the JSON x64 record layout, including padding;
it is not a case-local duplicate or a hard-coded byte count.

## Linkage backends

Contracts pass a stable generated identity to `win32.fastcall`. Linkage is a
separate include selected per function set or per DLL.

Recording backends map identities to deterministic integers for contract tests:

```asm
include 'backends/recording/downlevel/kernel32.g'
```

Microsoft COFF backends map identities to linker-visible external names.
External declarations are emitted from `postpone` only when actually used:

```asm
include 'backends/coff/downlevel/kernel32.g'
```

Direct PE backends map identities to unique IAT labels:

```asm
include 'backends/pe/downlevel/kernel32.g' ; before code

section '.idata' import data readable writeable
include 'backends/pe/downlevel_imports.g'  ; used entries only
```

The projection owns its small PE64 import materializer; merely including all
metadata does not emit unused DLLs or entry points.

## Focused contract example

With an x64 lowering provider installed:

```asm
include 'windows.g'
include 'backends/coff/downlevel/kernel32.g'
include 'contracts/downlevel/qualified/kernel32.g'
include 'contracts/downlevel/public/kernel32.g'

CreateProcessW ,,,,win32.BOOL.FALSE,\
  win32.PROCESS_CREATION_FLAGS.CREATE_NEW_CONSOLE,,,0,0
```

The generated contract supplies zero for the six optional positions and
requires the remaining four operands.

## Current lowering boundary

`runtime/fastcall_adapter.g` implements the stable target/list protocol by
adapting to an installed `fastcall` lowering macro. This makes the generated
surface usable with the existing x64 lineage and keeps PE/COFF linkage tests
real. It intentionally does not claim that the historical destructive
left-to-right argument setup is the final scheduler.

The register-retirement scheduler, GPR `xchg` permutation lowering, narrow
parameter promotion, and floating normalization remain specified by the other
documents in this directory and can replace the adapter without regenerating
any public function contract.
