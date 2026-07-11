# Win64 parameter scheduler

`win32.fastcall` is a bounded parallel-assignment problem. Its inputs are the
incoming CPU state and a list of source expressions; its required output is the
Win64 argument state at one call boundary. It is not correct to lower that list
from left to right.

The central invariant is:

> An ABI destination register may be overwritten only when no other pending
> argument or indirect target still reads its incoming physical register.

This scheduler belongs between generated function contracts and the
size-oriented move selector. Type/value resolution happens before it;
instruction-size selection happens after it.

Scalar floating normalization is specified separately in
[`FLOAT_ARGUMENTS.md`](FLOAT_ARGUMENTS.md). In particular, the function
contract selects the ABI lane; the source parser supplies representation and
dependency facts only.

## Normalized jobs

The generated contract supplies the declared ABI class and the number of low
bits that define the parameter value. These cannot be recovered reliably from
source syntax, because an immediate has no inherent parameter type and an
unqualified memory expression may have no size. Win64 supplies a 64-bit GPR or
stack container for scalar integer arguments; bits above the defined value are
deliberately unspecified and need not be preserved.

Each explicit or defaulted parameter is normalized to a job containing:

```text
source tokens
load kind          value | address | float32 bits | float64 bits | temporary
ABI outputs        GPR | XMM | GPR+XMM | stack
defined width      1 | 2 | 4 | 8 bytes of required low bits
source width       bytes that may safely be read from the source
source bit origin  normally bit 0; AH/CH/DH/BH are exceptional
legal write widths defined width through 8 bytes, filtered by source safety
relocatable         source requires backend relocation semantics
destination set    RCX/RDX/R8/R9, XMM0..3, and/or outgoing-stack offset
GPR read mask
XMM read mask
```

An ordinary indirect call target is a pinned pseudo-job: it remains a consumer
until the target has been materialized or the call is emitted. A direct COFF
external or PE import identity has no incoming-register reads.

COM dispatch is different. `{slot}` means "load the vtable through the final
object argument and call this slot." It consumes final RCX after parameter
setup, not incoming RCX during the scheduling graph.

For scalar FP jobs, ABI class and semantic width come from the generated
`Single`/`Double` contract (or an explicit raw-call override), never from
`@src.type`. An XMM source's parsed size of 16 is only its register-container
width. A GPR may be a bit source for an XMM destination, and a float-containing
small aggregate may legitimately remain a GPR-class job.

## Operand pre-scan

All jobs are parsed before any instruction is emitted. `x86.parse_operand`
provides scalar register and address information; the SSE parser provides XMM
register identity while retaining the GPRs used by a memory address.

- A register source reads its physical register. `CL`, `CX`, `ECX`, and `RCX`
  all conservatively read physical RCX. High-byte aliases need explicit
  canonicalization of x86-2's REX-forbidden register encoding.
- An XMM source reads its physical XMM register.
- A memory or address source reads every base and index GPR recorded in
  `@src.address_registers`.
- RIP/EIP-relative addressing does not read an incoming general register.
- An immediate, direct relocatable identity, or inline-data identity has no
  incoming-register read.

Registers bypass value and storage-type checks, but never dependency scanning.
An explicit register size remains an unchecked caller assertion, consistent
with register bypass. Writing any ABI destination width retires the entire
physical register because every bit above the parameter's defined low bits is
unused. The move selector may therefore promote a BYTE or WORD assignment to a
DWORD or QWORD operation when the wider encoding is smaller.

Promotion never authorizes a wider memory read. A byte object at the end of a
page must still be read as a byte; only the destination operation or a later
store may be widened. Low-aligned register sources can be read through a wider
alias because the extra source bits merely become unspecified destination
bits. High-byte registers are not low-aligned and cannot use that shortcut.

Promotion also does not replace a required language/type conversion. If a
typed source is narrower than the parameter's defined width, any required sign
or zero extension within those defined bits happens first. Raw register bypass
may leave that responsibility to the caller, but the optimizer may never
invent missing required bits.

`tests/fasm2-calm/operand_reads.asm` is the first executable proof of this
pre-scan. It checks register aliases, high-byte registers, base/index memory,
immediates, and RIP-relative addressing against x86-2 metadata.

## Read-count scheduling

The planner maintains a pending-read count for every physical GPR and XMM
register. An OR mask alone is insufficient because several jobs may consume
the same incoming value.

A register-output job targeting `D` is ready when:

```text
pending_reads[D] == (this job reads D ? 1 : 0)
```

The job may read and write the same register because an instruction evaluates
its source before committing its destination. Thus `RCX <- [RCX]` is ready,
while `RCX <- 1` is delayed if another job still needs incoming RCX.

After a job is appended to the plan, its source reads are retired and its ABI
destination is marked final. A final argument register is never scratch.
Stack-output jobs have no register destination and are normally ready first;
this preserves incoming values used by fifth and later arguments before the
first four argument registers are overwritten.

Examples:

```asm
win32.fastcall target,1,rcx
; first:  RDX <- incoming RCX
; second: RCX <- 1

win32.fastcall target,1,2,3,4,rcx
; first:  [outgoing argument 5] <- incoming RCX
; then:   RCX <- 1
```

GPR and XMM dependencies share one plan. A floating memory source can still
block a GPR destination through its base/index address.

## Pure GPR permutations

Closed GPR permutations are removed before general cycle handling. A component
is eligible only when every job is a direct, low-aligned GPR source, each
physical source occurs exactly once, and every non-permutation consumer of
those incoming registers has already retired. Memory, address, high-byte,
fan-out, XMM, and indirect-target dependencies are not GPR permutation jobs.
The x86 ISA has no XMM form of `xchg`; XMM cycles use the general hold path.

A two-GPR swap always emits one register-to-register `xchg`:

```asm
win32.fastcall target,rdx,rcx
; xchg rcx,rdx
```

It must never become three moves through a temporary. A longer cycle uses
exactly `N-1` register exchanges. For a cycle whose required mapping is:

```text
D0 <- D1, D1 <- D2, ... Dn-1 <- D0
```

one legal pivot sequence is:

```text
xchg D0,Dn-1
xchg D0,Dn-2
...
xchg D0,D1
```

The planner evaluates every possible pivot and legal common operation width,
then chooses the smallest encoded sequence. If all defined values are at most
32 bits, a 64-bit exchange is unnecessary; a WORD cycle can promote to DWORD
to remove the `66h` prefix. Every destination still receives its required low
bits, while the promoted upper bits remain unspecified. The Win64 argument
register set does not include RAX, so its compact accumulator `xchg` forms are
encoding facts rather than pivot candidates for this scheduler.

After emitting the exchange sequence, retire every source read and commit the
whole component atomically in the planner model. This keeps later scheduling
from treating an intermediate exchange state as an available argument value.

## Guaranteed R11 evacuation

The planner reserves R11 as its scalar scratch. It is volatile, is not a Win64
argument destination, and can carry integer, address, or floating-point bits.
Incoming R11 still belongs to the caller, however, and may be used by any
source or indirect target.

When the pre-scan finds incoming R11 consumers, the plan first evacuates them:

1. Store incoming R11 directly in a private `r11.in` slot.
2. Replace a direct R11 source with that saved slot.
3. For every memory/address expression that uses R11, reload `r11.in`, evaluate
   the complete expression into R11, store the result in a job-specific slot,
   and replace the job source with that slot.
4. Apply the same rule to an indirect call target that uses R11.

These pre-stage actions run before any ABI destination is changed, so all the
other incoming registers in each expression are intact. An instruction such as
`mov r11,[r11+r10*4]` or `lea r11,[r11+r10]` can consume incoming R11 as part
of its source while replacing it with the complete value. Once every such
expression is staged, R11 is guaranteed available to the scheduler.

Scalar Win64 parameters occupy at most 64 bits. `movd`/`movq` transfers let the
same evacuation path preserve floating-point bits without assigning an XMM
temporary. This is a correctness mechanism; the planner can omit it whenever
the pre-scan proves incoming R11 dead.

## General cycles and temporaries

If a full pass finds no ready job, the pending graph contains a cycle. Break it
by materializing one complete source expression, not by trying to rewrite
arbitrary source tokens:

```text
value         MOV/MOVZX scratch,source
address       LEA       scratch,[source]
float32 bits  MOVD      scratch32,source
float64 bits  MOVQ      scratch64,source
```

Replace that job's original reads with the temporary dependency and resume the
same readiness algorithm. This path is reserved for cycles that cannot be
expressed as a pure register permutation.

After the evacuation phase, R11 is the guaranteed scalar hold register. If a
hold must outlive another cycle break, store it in a job-specific slot and
release R11; a direct memory temporary contributes no incoming-register edge.
RAX and R10 are optional shorter alternatives only when their incoming values
are proven dead.

The planner records actions before encoding them. It can therefore count hold
slots, compute the complete outgoing frame once, and then replay:

```text
allocate fixed call frame
pre-stage/hold actions
argument assignments
backend call
release frame when the surrounding function does not own it
```

This is two-pass call lowering, not a general backend optimizer. Each hold
removes at least one dependency edge, so the bounded graph terminates.

## Stack and target rules

- The frame contains the 32-byte home area, stack arguments, and planner spill
  slots, rounded for call-site alignment.
- A containing function may reserve the maximum frame once. That fixed-frame
  mode is preferred when unwind metadata is required.
- Raw RSP-relative source expressions are defined relative to the allocated
  call frame, matching the current fastcall lineage. Code that needs pre-frame
  RSP state must use a stable frame pointer or materialize it before the call.
- General alias analysis is impossible. Private outgoing/spill slots are
  assumed not to alias user-provided source memory.
- Variadic floating arguments, when supported, are multi-destination jobs
  because Win64 requires the value in both the XMM and corresponding GPR
  position.
- COM target materialization happens after RCX is final. Ordinary indirect
  targets remain pinned consumers of their incoming registers.

Only after the plan is dependency-correct may the move selector use the
state-discarding size transformations described in `ABI_OPTIMIZATION.md`.
Manual register setup plus a direct `call` remains the explicit performance
path.

## Acceptance cases

The production scheduler needs byte/disassembly assertions for:

- chains, mandatory single-`xchg` two-register swaps, and longer register
  cycles using exactly `N-1` exchanges;
- pivot/rotation selection across the Win64 argument-register cycle;
- BYTE/WORD permutation promotion to a smaller common operation width;
- `[rcx]`, `[rcx+r9*4]`, and self-addressing `RCX <- [RCX]`;
- `&expression` dependencies;
- fifth and later arguments sourced from RCX/RDX/R8/R9;
- incoming R11 as a direct source, address component, and indirect target;
- XMM swaps and floating memory addressed through a GPR destination;
- 8/16/32/64-bit aliases, high-byte exclusions, and narrow memory sources that
  must not be over-read;
- absolute-immediate modulo cases versus relocatable values whose width may
  not change;
- RIP-relative, relocatable, and deliberately RSP-relative sources;
- PE import, COFF external, ordinary indirect, and COM vtable calls;
- a runtime callee that poisons unused carrier bits, then records/consumes only
  each parameter's defined low bits.
