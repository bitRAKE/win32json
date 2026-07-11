# Projection usage cases

These are end-to-end consumers of the generated projection. The fixtures under
`tests/fasm2-calm/` validate individual generation and lowering mechanisms;
these cases assemble, link where applicable, inspect, and execute final x64
Windows products.

Run all cases from the repository root:

```powershell
& .\cases\build.ps1
```

Products and `llvm-readobj` reports are written to `cases/out/`.

## Cases

| Case | Product trajectory | What it validates |
|---|---|---|
| `direct_pe_downlevel` | fasmg -> PE64 | Concrete DLL contract, direct-IAT backend, used-only import emission, loader execution |
| `coff_link_downlevel` | fasmg -> COFF -> `lld-link` + PSDK import libraries -> PE64 | Generated `sizeof WSAData`, COFF relocations, exact SDK export spellings, multi-DLL linkage, Win64 calls at runtime |
| `newcoff_link_downlevel` | fasmg -> NEWCOFF bigobj -> `lld-link` + PSDK import library -> PE64 | Format-aware facade routing, canonical bigobj records, CodeView, synthesized unwind data, linkage and execution |
| `direct_pe_apiset` | fasmg -> PE64 | Raw API-set function surface, short enum transform, API-set loader resolution |

The COFF case deliberately links against the newest installed Windows SDK
`um\x64` library directory. A JSON DLL/function mismatch therefore fails at
link time, while argument-contract or ABI mistakes are exposed when the image
runs. LLVM inspection additionally checks that only the requested imports made
it into each product. The SDK import library currently binds `WSAStartup` and
`WSACleanup` by WS2_32 ordinals 115 and 116; their JSON names are checked on the
COFF relocations and the SDK-selected ordinals are checked on the final PE.

The cases do not load `fasm2.inc`, asmgame's historical `fastcall`, or its
`windows.g`. They use the curated fasmg/x86-2 base and `proc64.inc` only for
`proc`/`endp` plus its static-RSP frame machinery. `fixed_call64.g` purges
proc64's historical argument mover before any calls are assembled. The focused
provider never adjusts RSP and rejects every operand form
outside the immediate/register subset exercised here; it is an honest seam
test, not a substitute for the unfinished production dependency scheduler.

Every body is wrapped in `proc`/`endp`. Ordinary cases use
`static_rsp_prologue`, `static_rsp_epilogue`, and `static_rsp_close`; the
NEWCOFF debug case wraps the same stable-frame model with
`newcoff_debug_prologue`/`newcoff_debug_close` so CodeView and unwind records
capture the final frame. The lowering provider reports a 32-byte home-area
requirement through `fastcall?.frame`; the procedure close pass combines it
with declared locals and emits one stable frame. Each case has its final
disassembly checked for exactly one RSP subtraction, a minimum
32-byte home area, and a frame size congruent to 8 modulo 16. Thus entry RSP is
aligned to 16 before calls, and hidden per-call stack adjustments are rejected
from the binary product rather than inferred from source macros.

The sources intentionally use raw function names. Contract includes choose the
API surface, while backend includes choose its linkage; consumer call sites do
not encode a DLL or API-set identity. Enum parameters likewise use their short
names because the generated function contract supplies the enum namespace.
This is why the API-set case says `RoInitialize RO_INIT_MULTITHREADED`, not a
qualified DLL/API-set name. `ExitProcess ERROR_SUCCESS` uses the same mechanism
through a reviewed semantic resolver for metadata's otherwise plain UInt32
exit-code parameter.

Generated setup is consolidated through one format-aware include:

```asm
define win32.select.downlevel kernel32,ws2_32
include 'generated/fasm2_calm/x64/windows.inc'
```

It chooses linkage from definite PE/legacy-COFF state or NEWCOFF's definite
relocation model, installs the selected contracts and raw aliases, and
postpones direct-PE `.idata` output. The cases do not include generated backend,
qualified-contract, public-contract, or import-materializer files directly.
