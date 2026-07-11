# Win64 call-boundary size optimization

The Win64 ABI creates a useful optimization boundary: immediately after the
call, flags and volatile registers are not part of the caller's preserved CPU
state.  The projection can therefore favor compact argument-materialization
sequences over throughput, provided that every source operand has the same
value at the call and the stack remains ABI-correct.

This is a size-and-functionality policy, not a performance optimizer.  The
call layer is nevertheless responsible for dependency-correct parameter
ordering.  A user who needs microarchitecture-specific scheduling can
materialize the arguments manually and issue the call directly.

Authoritative references:

- [Microsoft x64 calling convention](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention)
- [Microsoft x64 prolog and epilog rules](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog)
- [Intel 64 and IA-32 instruction-set manuals](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)

## The boundary is at the call

The ABI discontinuity does not make all volatile state immediately available
at the start of argument setup.  An operand later in the list may still read a
register that an earlier assignment wants to overwrite:

```asm
fastcall target,rdx,rcx       ; a destructive left-to-right swap is wrong
fastcall target,1,[rcx]       ; assigning RCX first changes the address
```

Destructive left-to-right setup is not an acceptable baseline.  The lowering
must inspect every operand before emitting parameter moves and retire incoming
register values only after their final consumer has executed.

## Register-retirement scheduler

The complete planner contract is specified in
[`CALL_SCHEDULER.md`](CALL_SCHEDULER.md). The summary here records the
optimization boundary.

Floating source semantics and ABI-lane selection are specified in
[`FLOAT_ARGUMENTS.md`](FLOAT_ARGUMENTS.md); they are normalized before this
size selector sees a bit-transfer job.

The pre-scan uses x86-2's operand parser to create one job per argument and one
job for an indirect call target. The generated parameter contract supplies the
ABI class and defined low-bit width; these are not inferred solely from source
syntax. Each job records:

```text
source form, safe read width, and bit origin
defined low-bit width and legal destination write widths
source GPR read mask
source XMM read mask
ABI destination register, or no register for a stack job
stack destination and value/type metadata
```

A register operand contributes its physical register to the read mask.  A
memory or address operand contributes every base/index register in
`@src.address_registers`.  Immediate and inline-data operands contribute no
register reads.  The indirect call target remains a consumer until the call or
until it is materialized into a safe location.

Scheduling is reference-count based:

1. Count every pending read of each incoming GPR and XMM register.
2. A stack-output job has no ABI register destination and can normally run
   immediately, subject to scratch-register availability.
3. A register-output job targeting `D` is ready when no *other* pending job
   needs the incoming value of `D`.  Its own source may read `D`; the emitted
   instruction reads before it writes.
4. Emit a ready job, decrement the read counts for its source, and mark its ABI
   destination final.
5. A volatile scratch register becomes available only when its incoming read
   count reaches zero and it is not holding an already-final argument.
6. Before general cycle handling, lower every closed direct-register
   permutation to `N-1` register-to-register `xchg` instructions. A two-node
   swap is always one `xchg`.
7. If no remaining job is ready, materialize one complete source expression
   into an available scratch register or a fixed call-frame spill slot.
   Replace that job's read set with the materialized source and continue. This
   breaks memory/address and mixed-source cycles uniformly.

For example, `target,rdx,rcx` first preserves one source, then performs the
other move, then consumes the preserved value.  `target,1,[rcx]` evaluates the
memory job before retiring the incoming RCX.  RAX/R10/R11 are preferred cycle
scratch registers only after the pre-scan proves their incoming values dead;
otherwise the fixed spill slot is the correctness fallback.

This is still much smaller than a general code generator: it schedules a
bounded set of ABI assignments and does not optimize across the call.

## Explicit optimization policy

Compact substitutions are legal only when their side effects are authorized.
The call-lowering context needs these independent facts:

```text
flags_dead              condition flags may be overwritten
volatile_gpr_scratch    per-register incoming read count reached zero
volatile_xmm_scratch    per-register incoming read count reached zero
below_rsp_scratch       a balanced push/pop may touch [rsp-8]
transient_rsp_ok        asynchronous unwind can recover across push/pop
normal_stack_memory     destination is an ordinary allocated stack slot
fixed_call_frame        shadow/stack-argument area is allocated and unwind-safe
defined_value_bits      required low bits for this scalar parameter
safe_source_bits        bits that may be read without widening a memory object
```

These are semantic permissions and per-job facts, not general optimization
levels. In particular, `flags_dead` does not imply `below_rsp_scratch`, and
neither makes an arbitrary memory read-modify-write equivalent to a store.
Narrow-width promotion follows `defined_value_bits` and `safe_source_bits`; it
is not a global setting.

## Narrow scalar parameters

For a scalar integer parameter narrower than eight bytes, only the declared
low bits define the value delivered to the callee. The remainder of its GPR or
eight-byte outgoing slot is unspecified. The move selector may enumerate wider
destination operations and select the shortest legal encoding.

Examples include using `mov ecx,edx` instead of `mov cx,dx`, storing `r8d`
instead of `r8w` into a WORD argument slot, or using a DWORD `xchg` for a WORD
register permutation. No particular sign- or zero-extension is required above
the defined width. An immediate representative only needs to be congruent to
the requested value modulo that width.

Source safety is separate:

- A low-aligned register may be read through a wider alias; the added bits are
  allowed to be arbitrary.
- AH/CH/DH/BH cannot be promoted as though they were AL/CL/DL/BL because their
  value begins at bit 8.
- A memory operand is never read wider than its definite object/source width.
  A wider destination store may follow an exact-width load through scratch.
- A conversion from a typed source narrower than the parameter is completed
  within the required low bits before carrier-width promotion. Promotion does
  not replace `movsx`/`movzx` semantics when those bits are significant.
- Addresses, pointers, relocations, and other full-width identities retain
  their full required width.
- Variadic/default language promotions establish the effective parameter width
  before this ABI encoding optimization runs.
- A narrower operation remains valid when it is already the smallest encoding;
  promotion is permission to compare candidates, not a mandate to widen.

The existing x86-2 settings save/restore mechanism suggests an eventual
annotated form such as `{win64.call} mov ...`.  Until MOV consumes an explicit
policy, a dedicated fastcall move selector is safer than changing every MOV in
the assembler.

## Candidate transformations

| Requested assignment | Compact sequence | Required permission | Notes |
|---|---|---|---|
| two-GPR value swap | `xchg reg,reg` | closed direct-register permutation | Mandatory; never lower through a temporary. |
| `N`-GPR value cycle | `N-1` register `xchg`s | closed direct-register permutation | Choose pivot and common legal width by encoded size. |
| `r64 = 0` | `xor r32,r32` | `flags_dead` | Exact full-register zero, 2-3 bytes. |
| `r64 = signed imm8` | `push imm8` / `pop r64` | `below_rsp_scratch`, `transient_rsp_ok` | 3-4 bytes; stack pointer is restored before the call. |
| `r64 = signed imm32` | normal `mov r64,imm32` | none | x86-2 already selects the sign-extended C7 form. |
| `r64 = definite 0..FFFFFFFFh` | `mov r32,imm32` | none | Exact 64-bit result; exclude relocations and explicitly forced imm64 encodings. |
| narrow register copy | wider low-aligned register `mov` | wider form encodes smaller | Preserve the defined low bits; upper container bits are unspecified. |
| narrow outgoing-slot store | wider register store | wider form encodes smaller, source is a register | Does not permit a wider read from source memory. |
| narrow absolute immediate | any shorter congruent representative | definite non-relocatable value | The encoded result must match every defined low bit. |
| stack slot `= 0` | `and qword [slot],0` | `flags_dead`, `normal_stack_memory` | Smaller, but becomes a read-modify-write. |
| stack slot `= -1` | `or qword [slot],-1` | `flags_dead`, `normal_stack_memory` | Same read-modify-write caveat. |
| stack slot `= signed imm8` | `push imm8` / `pop qword [slot]` | `below_rsp_scratch`, `transient_rsp_ok`, `normal_stack_memory` | Relies on POP's RSP-addressing rule. |
| destination already contains source | emit nothing | required low bits already present | For a narrow parameter, clearing unused upper bits has no value. |

The stack RMW forms are never valid substitutions for arbitrary memory.  They
change flags, perform a read, and have different concurrency/MMIO behavior.
Their use is limited to private call-frame slots.

Balanced push/pop is likewise not justified by writable lower stack alone.
An asynchronous unwind may observe RSP between the two instructions.  The
substitution therefore requires a frame/unwind scheme that can recover from
the transient displacement, or an explicit no-asynchronous-unwind policy.

For a promoted immediate, sign extension is checked modulo the complete
defined width. For example, `push -128` represents BYTE `80h` and WORD
`FF80h`, but not WORD `0080h`. A relocation is never treated as a small
absolute value based on its current assembly-pass placeholder; changing its
width could change the PE/COFF relocation kind or truncate an address.

## Findings from the prior fastcall experiment

The attached iteration contains several sound ideas:

- bypassing an argument already in its ABI register;
- zeroing ABI registers with their 32-bit XOR forms;
- using balanced push/pop pairs for small immediates;
- using compact RMW forms for private stack slots;
- treating RAX as a scratch register once its previous value is no longer a
  source operand.

Before it becomes the production lowering path, these cases need tightening:

1. Definite immediates outside the accepted 32/64-bit ranges currently have
   branches where no instruction and no error is emitted.
2. Register bypass must include width semantics. Omitting `mov ecx,ecx` is
   valid when its required low bits are already present; promoted upper bits
   are explicitly irrelevant, but required low bits are not.
3. Register permutations require direct `xchg` lowering, while memory addresses
   based on ABI destination registers require the retirement scheduler above;
   the prior loop implements neither rule.
4. Scratch RAX cannot be used until later operands are known not to consume
   its incoming value.
5. Float immediates in stack positions need explicit dword/qword stores and
   byte-checked fixtures.
6. Dynamic `sub rsp`/`add rsp` around a call is not enough for unwindable
   functions.  The call frame should be incorporated into the function's
   described fixed frame when unwind metadata is required.
7. The current external fastcall lineage contains a duplicated dword register
   move; the prior exact-register bypass removes it, but that bypass should be
   tested rather than copied as an unscoped textual optimization.

## Implementation seam

Keep the layers narrow:

1. Generated function/method contracts resolve defaults and symbolic values.
2. `win32.fastcall` resolves PE/COFF or vtable linkage.
3. The Win64 fastcall layer parses all operands and schedules register
   retirement, including cycle breaks.
4. A size-oriented move selector receives each scheduled source, definite
   destination, and explicit permissions above.
5. x86-2 remains the final encoder and handles ordinary MOV encodings.

This makes the complex knowledge testable in one place without coupling the
metadata projection to opcode selection.  Moving the selector into x86-2's
MOV is reasonable later, but only if the policy remains explicit and scoped.
The existing x86-2 `{settings} instruction` save/restore path is the preferred
seam; replacing or moving the root `mov?`/`??` interceptors after inclusion
would create fragile ownership and include-order dependencies.

## Required fixtures

The optimizer should not be accepted on successful assembly alone.  Tests
must assert emitted bytes or disassembly for:

- RCX/R8 zero and signed-imm8 cases;
- signed-imm32 and unsigned-imm32 boundaries;
- fifth and later stack arguments at disp8 and disp32 offsets;
- stack values `0`, `-1`, `-128`, `127`, `128`, and 64-bit constants;
- float32/float64 register and stack positions;
- exact-register bypass for 8/16/32/64-bit GPRs and XMM registers;
- relocatable immediates, addresses, and memory operands;
- mandatory register `xchg` swaps, longer permutation cycles, and
  address-dependency cases;
- narrow register/stack promotion versus forbidden memory-source over-read;
- promoted-immediate boundaries such as WORD `FF80h` versus `0080h`;
- absolute constants versus COFF/PE relocations whose width must remain fixed;
- variadic/default promotions before carrier-width selection;
- RAX/R10/R11 as live later sources while scratch is needed;
- indirect call targets held in registers or register-based memory;
- frame reuse versus transient frame allocation;
- PE import, COFF external, and COM vtable call targets.

`tests/fasm2-calm/fastcall_size.asm` establishes the initial byte-size facts.
The next fixture should exercise the selector itself and deliberately test all
error paths before it replaces the existing fastcall lowering.
