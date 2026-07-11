; Floating-source normalization facts. The function contract chooses the ABI
; lane; operand parsing only describes how the supplied bits can be obtained.

format binary
use AMD64
use64

; Parser kind codes emitted by the descriptor fixture.
PARSER_IMMEDIATE = 1
PARSER_GPR = 2
PARSER_XMM = 3
PARSER_MEMORY = 4

calminstruction emit_parser_descriptor operand*
	local kind
	call SSE.parse_operand@src,operand
	compute kind,0
	check @src.type = 'imm'
	jyes immediate
	check @src.type = 'reg'
	jyes gpr
	check @src.type = 'mmreg'
	jyes xmm
	check @src.type = 'mem'
	jyes memory
	jump ready
immediate:
	compute kind,PARSER_IMMEDIATE
	jump ready
gpr:
	compute kind,PARSER_GPR
	jump ready
xmm:
	compute kind,PARSER_XMM
	jump ready
memory:
	compute kind,PARSER_MEMORY
ready:
	emit 1,kind
	emit 1,@src.size
end calminstruction

; The historical call-level marker must be removed before parser dispatch.
; This macro emits marker-present plus the normalized parser descriptor.
macro emit_call_descriptor? argument&
	match =float? value,argument
		db 1
		emit_parser_descriptor value
	else
		db 0
		emit_parser_descriptor argument
	end match
end macro

; Floating values are unsized. The directive/emitter selects IEEE width.
.emit4_from_suffixed_float:
	dd 1.0f
load .single_bits:4 from .emit4_from_suffixed_float
assert .single_bits = 3F800000h

.emit8_from_suffixed_float:
	dq 1.0f
load .double_bits:8 from .emit8_from_suffixed_float
assert .double_bits = 3FF0000000000000h

.emit4_from_unsuffixed_float:
	dd 1.0
load .converted_single_bits:4 from .emit4_from_unsuffixed_float
assert .converted_single_bits = 3F800000h

.emit8_from_unsuffixed_float:
	dq 1.0
load .converted_double_bits:8 from .emit8_from_unsuffixed_float
assert .converted_double_bits = 3FF0000000000000h

; SSE.parse_operand recognizes source containers, not scalar interface types.
.parser_descriptors:
	emit_parser_descriptor 1.0f
	emit_parser_descriptor 1.0
	emit_parser_descriptor dword 1.0
	emit_parser_descriptor qword 1.0
	emit_parser_descriptor xmm2
	emit_parser_descriptor eax
	emit_parser_descriptor r9
	emit_parser_descriptor dword [rax]
	emit_parser_descriptor qword [rax]
	emit_parser_descriptor [rax]

load .literal_f_kind:1 from .parser_descriptors + 0
load .literal_f_size:1 from .parser_descriptors + 1
load .literal_plain_kind:1 from .parser_descriptors + 2
load .literal_plain_size:1 from .parser_descriptors + 3
load .literal_dword_size:1 from .parser_descriptors + 5
load .literal_qword_size:1 from .parser_descriptors + 7
load .xmm_kind:1 from .parser_descriptors + 8
load .xmm_container_size:1 from .parser_descriptors + 9
load .eax_kind:1 from .parser_descriptors + 10
load .eax_size:1 from .parser_descriptors + 11
load .r9_size:1 from .parser_descriptors + 13
load .memory_dword_size:1 from .parser_descriptors + 15
load .memory_qword_size:1 from .parser_descriptors + 17
load .memory_unsized_size:1 from .parser_descriptors + 19

assert .literal_f_kind = PARSER_IMMEDIATE
assert .literal_f_size = 0
assert .literal_plain_kind = PARSER_IMMEDIATE
assert .literal_plain_size = 0
assert .literal_dword_size = 4
assert .literal_qword_size = 8
assert .xmm_kind = PARSER_XMM
assert .xmm_container_size = 16
assert .eax_kind = PARSER_GPR
assert .eax_size = 4
assert .r9_size = 8
assert .memory_dword_size = 4
assert .memory_qword_size = 8
assert .memory_unsized_size = 0

.call_annotation_descriptors:
	emit_call_descriptor float dword 1.0
	emit_call_descriptor 1.0f

load .float_marker_present:1 from .call_annotation_descriptors + 0
load .stripped_float_kind:1 from .call_annotation_descriptors + 1
load .stripped_float_size:1 from .call_annotation_descriptors + 2
load .literal_marker_present:1 from .call_annotation_descriptors + 3
load .unmarked_literal_kind:1 from .call_annotation_descriptors + 4
load .unmarked_literal_size:1 from .call_annotation_descriptors + 5

assert .float_marker_present = 1
assert .stripped_float_kind = PARSER_IMMEDIATE
assert .stripped_float_size = 4
assert .literal_marker_present = 0
assert .unmarked_literal_kind = PARSER_IMMEDIATE
assert .unmarked_literal_size = 0

; A fixed-prototype FLOAT32 contract selects XMMn. Literal bits can be staged
; through a GPR, but the GPR source does not change the contract-selected lane.
.materialize_float32:
	mov eax,1.0f
assert $ - .materialize_float32 = 5
load .materialized_float32_bits:4 from .materialize_float32 + 1
assert .materialized_float32_bits = 3F800000h

.transfer_float32_to_xmm:
	movd xmm0,eax
assert $ - .transfer_float32_to_xmm = 4

.materialize_float64:
	mov rax,1.0f
assert $ - .materialize_float64 = 10
load .materialized_float64_bits:8 from .materialize_float64 + 2
assert .materialized_float64_bits = 3FF0000000000000h

.transfer_float64_to_xmm:
	movq xmm1,rax
assert $ - .transfer_float64_to_xmm = 5

; Fifth and later arguments use eight-byte ABI slots, but only four bytes of a
; FLOAT32 value are significant. FLOAT64 consumes the complete slot.
.store_float32_stack:
	mov dword [rsp+20h],eax
assert $ - .store_float32_stack = 4

.store_float64_stack:
	mov qword [rsp+20h],rax
assert $ - .store_float64_stack = 5
