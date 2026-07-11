; Minimal fasmg/x86-2 demonstration that floating values are unsized until a
; consumer requests an output width.

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
