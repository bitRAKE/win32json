# Minimal case: fasmg floating values are unsized

This case demonstrates the intended fasmg numeric model. Floating values, like
native arbitrary-size integers, have no binary32/binary64 storage size until a
consumer requests one.

The earlier projection claim that `1.0f` implied binary32 and `1.0` implied
binary64 was incorrect. The trailing `f` does not create a C-style `float`
type.

## Environment

```text
fasmg version: flat assembler version g.l7xm
fasm2 commit:  9b3b97e38dff22668b1fd76a673451cdf008a7a8
include:       fasm2/include/x86-2.inc
```

## Minimal source

The standalone source is
[`float_literal_unsized.asm`](../../tests/fasm2-calm/float_literal_unsized.asm).

```asm
include 'x86-2.inc'

format binary

calminstruction emit_descriptor operand*
	local is_float,expression_size
	compute is_float,0
	check operand eqtype 0.0
	jno type_ready
	compute is_float,1
type_ready:
	compute expression_size,sizeof operand
	call x86.parse_operand@src,operand
	emit 1,is_float
	emit 1,expression_size
	emit 1,@src.size
end calminstruction

; Both descriptors are: floating-kind=1, sizeof=0, parser-size=0.
emit_descriptor 1.0f
emit_descriptor 1.0

; Both values convert according to the requested EMIT width.
emit 4: 1.0f
emit 8: 1.0f
emit 4: 1.0
emit 8: 1.0
```

With the fasm2 include directory in `INCLUDE`:

```powershell
$env:INCLUDE = 'C:\git\fasm2\include'
& 'C:\git\fasm2\fasmg.exe' `
  '.\float_literal_unsized.asm' `
  '.\float_literal_unsized.bin'
Format-Hex '.\float_literal_unsized.bin'
```

## Output

```text
01 00 00  01 00 00
00 00 80 3F
00 00 00 00 00 00 F0 3F
00 00 80 3F
00 00 00 00 00 00 F0 3F
```

| Bytes | Source | Meaning |
|---|---|---|
| `01 00 00` | descriptor for `1.0f` | floating value, `sizeof=0`, parser `size=0` |
| `01 00 00` | descriptor for `1.0` | floating value, `sizeof=0`, parser `size=0` |
| `00 00 80 3F` | `emit 4: 1.0f` | requested binary32 encoding |
| `00 00 00 00 00 00 F0 3F` | `emit 8: 1.0f` | requested binary64 encoding |
| `00 00 80 3F` | `emit 4: 1.0` | requested binary32 encoding |
| `00 00 00 00 00 00 F0 3F` | `emit 8: 1.0` | requested binary64 encoding |

The first six bytes establish that both expressions are floating numeric values
and neither has a size. The remaining bytes establish that the consumer's
requested width controls IEEE encoding for either spelling.

## Consequence for a typed call projection

The call interface supplies the size request:

```text
formal parameter Single   -> emit/materialize at 4 bytes
formal parameter Double   -> emit/materialize at 8 bytes
explicit dword/qword      -> request 4/8 bytes in a raw call
instruction destination   -> request its operand width
```

No literal-spelling recovery is needed. This keeps floating immediates aligned
with fasmg's arbitrary-precision integer model: value first, size only at the
final encoding boundary.

