# fasm2/CALM focused tests

`interface_contract.asm` exercises the boundary between generated interface
contracts and the existing COM-aware x64 `fastcall` macro:

- inherited vtable slots;
- a generated exact parameter contract replacing the generic fallback;
- interface-scoped public values and an internal CALM resolver;
- direct method and `object->Method` routing;
- deliberate register bypass;
- ordinary COFF linkage transformation through the same adapter;
- zero-size interface storage tags.

This is a contract/linkage routing test, not acceptance of the historical
macro's left-to-right parameter lowering. Scheduler correctness is specified
separately by `generated/fasm2_calm/CALL_SCHEDULER.md`.

Current assembly command:

```powershell
$env:INCLUDE = "C:\git\win32json;C:\git\!bitRAKE\asmgame\include;C:\git\!bitRAKE\asmgame\fasm2\include;$env:INCLUDE"
& 'C:\git\!bitRAKE\asmgame\fasm2\fasmg.exe' "-iInclude('fasm2.inc')" -n `
  'C:\git\win32json\tests\fasm2-calm\interface_contract.asm' `
  "$env:TEMP\win32json-interface-contract.obj"
```

Or run `verify-interface-contract.ps1`, which additionally disassembles the
object and checks the vtable offsets, symbolic values, register pass-through,
and COFF relocation.

The fixture uses `windows.g` from that existing toolchain because it owns the
COM-aware `fastcall {vtable-offset},args...` implementation.  The resulting
COFF object should have calls through offsets `10h` (`IUnknown::Release`) and
`18h` (`ITest::SetMode`).  The two symbolic `SetMode` spellings should lower
identically, and the register case should pass `r10d` through to the normal
fastcall operand lowering.  The final projected call should contain one
`IMAGE_REL_AMD64_REL32` relocation against `TestTarget`.

`fastcall_size.asm` asserts the byte lengths behind the proposed
size-oriented argument moves (`xor`, push/pop, stack RMW stores, register
`xchg`, narrow-value promotion, and x86-2's ordinary immediate MOV choices).
Run `verify-fastcall-size.ps1`, or assemble it directly:

```powershell
$env:INCLUDE = 'C:\git\fasm2\include'
& 'C:\git\fasm2\fasmg.exe' "-iInclude('dd.inc')" `
  "-iInclude('x86-2.inc')" `
  'C:\git\win32json\tests\fasm2-calm\fastcall_size.asm' `
  "$env:TEMP\win32json-fastcall-size.bin"
```

`minimal_base.asm` proves the curated implementation baseline can emit a
Microsoft x64 COFF object using only `dd.inc`, `align.inc`, `format.inc`,
`x86-2.inc`, and `macro/struct.inc`. It also verifies that `fix`, `times`,
`invoke`, and `addr` remain available as ordinary symbols. Run it with
`verify-minimal-base.ps1`.

`operand_reads.asm` is the first scheduler fixture. It calls x86-2's operand
parser without emitting instructions and verifies GPR read masks for physical
register aliases (including a high-byte register), memory base/index terms,
immediates, and RIP-relative addressing. It also checks XMM identity through
the SSE parser. Run it with
`verify-operand-reads.ps1`.

`float_operands.asm` proves why floating arguments have a separate
normalization path: suffixed and unsuffixed real literals both parse as unsized
immediates, XMM parsing exposes a 16-byte container rather than scalar width,
and GPR parsing carries no integer-versus-float meaning. It also asserts the
unsized-float model, width-selected IEEE bits, GPR-to-XMM transfers, and
FLOAT32/FLOAT64 outgoing-slot stores. Run it with
`verify-float-operands.ps1`.

`float_literal_unsized.asm` is the deliberately minimal author-facing
reproduction: one `x86-2.inc` include, two three-byte descriptors, and four
width-selected floating emissions. Its explanation is in
`generated/fasm2_calm/FASMG_UNSIZED_FLOATS.md`.

Generated projection acceptance is split into focused checks:

- `verify-generated-contract.ps1` checks `CreateProcessW` defaults, required
  positions, short and qualified typed values, and canonical/public parity.
- `verify-generated-collision.ps1` checks the explicit DSOUND `GetDeviceID`
  selector while retaining qualified access to the TBS contract.
- `verify-generated-surfaces.ps1` assembles every down-level and API-set public
  contract and verifies that selecting both flat surfaces is rejected.
- `verify-generated-coff.ps1` checks the real `IMAGE_REL_AMD64_REL32`
  relocation and that unused externals do not leak into the object.
- `verify-generated-pe.ps1` checks a direct PE image contains exactly the used
  `KERNEL32.dll!GetCurrentProcessId` import from the generated import backend.
