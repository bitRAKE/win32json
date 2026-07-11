# Standard fasm2 projection usage cases

These cases consume `generated/fasm2/x64`, the conventional flat fasm2
projection. They intentionally use standard fasm2 `fastcall`, generated
parameter counts, flat equates/types, and generated PE import tables. The
first-class function/CALM projection is exercised separately by
[`cases_calm/`](../cases_calm/README.md).

Run the complete regular projection trajectory:

```powershell
& .\cases\build.ps1
```

Products and LLVM reports are written to `cases/out/`.

| Case | Product trajectory | Regular projection surfaces exercised |
|---|---|---|
| `direct_pe_downlevel` | fasmg -> PE64 | Flat `ERROR_SUCCESS`, KERNEL32 pcount, generated used-only import table |
| `direct_pe_apiset` | fasmg -> PE64 | Flat `RO_INIT_MULTITHREADED`, API-set pcounts and generated API-set imports |
| `coff_link_downlevel` | fasmg -> COFF -> PSDK/`lld-link` -> PE64 | Flat equates, selective generated `WSAData`, DLL pcounts, PSDK symbol linkage |
| `newcoff_link_downlevel` | fasmg -> NEWCOFF bigobj -> PSDK/`lld-link` -> PE64 | Flat equates/pcounts, CodeView, unwind synthesis, PSDK symbol linkage |

The regular projection does not create first-class API instructions. Calls
therefore retain the standard spelling:

```asm
fastcall [ExitProcess],ERROR_SUCCESS ; direct PE import
fastcall ExitProcess,ERROR_SUCCESS   ; COFF external
```

That visible call syntax is the key distinction from `cases_calm`, where the
generated contract itself is invoked as `ExitProcess ERROR_SUCCESS`.

Flat generated equates are included before the format statement. The regular
projection contains formatter-name constants too, so this ordering lets the
selected formatter resolve those names from the same flat symbol surface.
Types and parameter counts are installed after format and macro selection.

Direct PE cases pair `imports/library.inc` with `imports/all.inc`, or the two
API-set equivalents. The regular import library lists every DLL and relies on
each generated import block to establish its `.redundant` state; used-symbol
filtering still ensures that only referenced DLLs/functions reach the image.
