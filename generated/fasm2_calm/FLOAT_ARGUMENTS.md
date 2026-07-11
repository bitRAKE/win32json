# Floating argument normalization

Floating arguments are not ordinary integer jobs with a different move
mnemonic. Three independent facts must survive normalization:

```text
function contract     scalar float, scalar double, aggregate, integer bits...
ABI lane policy       XMM, GPR, stack, or duplicated XMM+GPR
source representation literal, GPR bits, XMM container, or memory object
```

`x86.parse_operand` and `SSE.parse_operand` describe only the last item. They
cannot determine what a function interface means or where the ABI requires the
value.

## Contract selects the lane

For a fixed-prototype Win64 call, the generated function/method contract first
classifies each formal parameter:

- native `Single` is a scalar FLOAT32 value;
- native `Double` is a scalar FLOAT64 value;
- integer, pointer, enum, and raw-bit parameters remain integer class;
- a small by-value aggregate follows the ABI's aggregate classification even
  when all of its fields happen to be floats;
- a COM method's hidden object pointer occupies the first ordinal before its
  explicit parameters are classified.

The ordinal then selects the carrier. A scalar FP parameter in position 1..4
uses XMM0..XMM3 at the matching position; it is not packed into the next free
XMM register. Position 5 and later uses the corresponding outgoing stack slot.
Thus a mixed signature `(integer, Single)` uses RCX and XMM1.

The local OpenGL metadata follows this rule. `glClearColor` declares four
`Single` parameters, while `glClearDepth` declares one `Double`; none declares
scalar floating transport through a GPR. Signatures such as `glBitmap` also
demonstrate ordinal alignment: its third/fourth scalar floats use XMM2/XMM3 and
its fifth/sixth floats use stack slots.

Float-like data can legitimately use a GPR without being a scalar FP ABI
parameter:

- an eight-byte `D2D_POINT_2F` passed by value is a small aggregate containing
  two floats and is classified as an aggregate/integer carrier;
- `ID3D12GraphicsCommandList::Set*Root32BitConstant` declares `SrcData` as
  `UInt32`; interpreting those bits as FLOAT32 does not change its GPR lane.

The normalized contract therefore records the lane explicitly. It never
infers XMM versus GPR from whether the source was written as an XMM register, a
GPR, or a floating literal. A genuinely nonstandard interface needs an
explicit generated lane override.

## Source descriptor

Each floating-capable job records:

```text
semantic class       integer | fp-scalar | aggregate | raw-bits
semantic width       4 (binary32) | 8 (binary64)
lane policy          ABI | XMM | GPR-bits | XMM+GPR duplicate | stack
source form          immediate | GPR | XMM | memory | temporary
source storage width 0 | 1 | 2 | 4 | 8 | 16
numeric kind         integer | floating | symbolic/relocatable
requested FP width   none | 4 | 8
width origin         contract | qualifier | vararg policy | instruction
conversion           emit-at-width | bit-copy | numeric-convert
GPR/XMM read masks
memory address GPR mask
```

The function contract normally supplies semantic class, requested width, and
`ABI` lane policy. Raw/untyped calls may supply explicit annotations. Source
parsing then fills only numeric kind, representation, storage width, and
dependency information.

An XMM operand parses as a 16-byte `mmreg`; this is its container width, not a
scalar FLOAT32/FLOAT64 declaration. A GPR likewise carries bits without saying
whether they represent an integer or a floating value. Sized memory identifies
how many bytes may be read, while unsized memory needs the typed contract or an
explicit source qualifier.

## Unsized floating values

x86-2 reports both `1.0f` and `1.0` as unsized floating immediates:

```text
@src.type = 'imm'
@src.size = 0
@src.imm eqtype 0.0
```

This is not lost precision metadata. It is fasmg's native numeric model:
floating values, like arbitrary-size integers, do not acquire a storage size
until a consumer requests one. The following spellings are floating numeric
values but do not select binary32 or binary64:

```text
1.0f
1f
1.0
```

The trailing `f` participates in floating-number syntax; it is not a C-style
single-precision type suffix. There is no reason for the projection to
stringify or preserve its spelling to recover a size.

Size comes from the consuming context:

```text
Single contract     request 4-byte IEEE emission
Double contract     request 8-byte IEEE emission
dword 1.0f          explicit 4-byte operand request
qword 1.0f          explicit 8-byte operand request
dd / emit 4         request 4-byte output
dq / emit 8         request 8-byte output
mov eax,1.0f        destination requests 4-byte encoding
mov rax,1.0f        destination requests 8-byte encoding
```

The same internally extended floating value is rounded/encoded directly at
the requested width. A runtime register or memory width mismatch is different:
FLOAT32-to-FLOAT64 still requires a real numeric conversion and is not silently
replaced by MOVD/MOVQ bit transport.

An integer immediate supplied to a floating contract remains a raw bit-pattern
case unless its syntax makes it a floating numeric value. Write a floating form
such as `1.0` or `1.0f`, not integer `1`, when the desired value is floating
one.

## The explicit `float` marker

Generated typed functions do not need a placement marker:

```asm
glClearColor 0.02f,0.02f,0.04f,1.0f
```

The `Single` contracts already select XMM0..XMM3 and binary32 semantics.

Raw calls and incompletely typed function pointers still need an override. The
historical form remains useful conceptually:

```asm
win32.fastcall target,float dword 1.0
```

It must be recognized by the call grammar before invoking the operand parser.
`float dword 1.0` is not one x86 operand, and passing it directly to
`SSE.parse_operand` fails. Moreover, fasmg also has a unary `float` numeric
operator, so parser output cannot reveal whether the call-placement marker was
present after normalization.

The marker means "scalar FP ABI class at this ordinal" and then delegates width
selection to the function contract, an explicit dword/qword qualifier, a typed
memory tag, or another explicit width. It is redundant on a typed scalar-FP
formal and an error when it conflicts with a definite non-FP contract unless
the caller uses a deliberate reinterpretation form.

For a raw call, `float 1.0f` and `float 1.0` are both unsized. Without a typed
formal they need an explicit FLOAT32/FLOAT64 request, just like an unsized XMM
or memory source. The parsed 16-byte XMM container is not a safe scalar-width
default.

For integer contracts carrying IEEE bits, use an explicit raw representation
such as the provisional form:

```asm
bits32 1.0f
```

This encodes binary32 bits but preserves the contract-selected GPR/stack lane.
Source spelling alone must never turn an integer formal into an XMM argument.

## Materialization

Typical scalar actions are:

```text
floating value requested as FLOAT32 -> r32 bits -> MOVD XMMn,r32
floating value requested as FLOAT64 -> r64 bits -> MOVQ XMMn,r64
GPR bits        -> MOVD/MOVQ XMMn,GPR
XMM source      -> scalar-width-compatible XMM copy
memory source   -> exact-width load/copy; never over-read
stack FLOAT32   -> write required low 4 bytes of its 8-byte ABI slot
stack FLOAT64   -> write all 8 bytes
```

The size optimizer may choose a wider XMM/GPR transfer when all additional
carrier bits are unused, just as for narrow integers. It may not widen a memory
read or replace a required numeric conversion with bit movement. Floating zero
may use an XMM zeroing idiom under the normal dependency rules; unlike integer
XOR, common XMM XOR forms do not alter integer condition flags.

For Microsoft x64 variadic or unprototyped calls, the call policy must first
establish the effective width and apply any desired C-style default promotion;
the literal itself supplies no FLOAT32 type to promote. An FP value in the
first four positions then also needs the matching GPR copy. This is a
multi-destination job, not a source-parser inference. Current win32json
function records do not reliably preserve ellipsis/varargs information, so
width selection, promotion, and duplication require added metadata or an
explicit call override before they can be generated safely.

## Scheduler integration

- A GPR bit source contributes a GPR incoming dependency even when the final
  lane is XMM.
- An XMM source contributes an XMM dependency; scalar width comes from the
  contract, not the parsed 16-byte container size.
- Floating memory contributes every address GPR plus its exact source width.
- XMM destinations are retired with the same read-count rule as GPR
  destinations.
- XMM permutations cannot use `xchg` and use the general hold path.
- A small float-containing aggregate in a GPR participates in ordinary GPR
  scheduling and permutation logic because its ABI class is not scalar FP.
- A variadic duplicated argument has both an XMM and a GPR destination mask.

These distinctions keep interface semantics, ABI placement, and instruction
encoding independent while still allowing the final move selector to optimize
the chosen bit transfers.

## Focused acceptance cases

- `1.0f`, `1f`, and `1.0` remaining unsized until a contract, qualifier, or
  instruction requests width;
- exact binary32/binary64 output from the same floating value at requested
  widths;
- XMM container width versus scalar semantic width;
- GPR bits passed to a `Single` contract and moved into the position-matched
  XMM register;
- `bits32 1.0f` retained in a GPR for an integer/raw-bits contract;
- mixed integer/Single signatures and COM hidden-object ordinal shifts;
- fifth and later FLOAT32/FLOAT64 stack slots;
- exact-width memory reads and explicit numeric-conversion rejection;
- small float-containing aggregate GPR classification;
- variadic XMM+GPR duplication when reliable metadata is available.

`tests/fasm2-calm/float_operands.asm` establishes the initial parser, literal,
bit-materialization, and stack-store facts against x86-2.

The distilled standalone reproduction is in
[`FASMG_UNSIZED_FLOATS.md`](FASMG_UNSIZED_FLOATS.md).
