; Focused proof that x86-2 exposes enough operand metadata for a parameter
; pre-scan to collect incoming GPR dependencies before emitting any moves.

format binary
use64

calminstruction gpr_reads operand*
	local mask,index,reg
	compute mask,0
	call x86.parse_operand@src,operand

	check @src.type = 'reg'
	jyes register
	check @src.type = 'mem'
	jno done

	compute index,1
memory_term:
	check index > elementsof @src.address_registers
	jyes done
	check index metadataof @src.address_registers relativeto x86.r64 | \
	      index metadataof @src.address_registers relativeto x86.r32
	jno next_memory_term
	compute reg,index metadataof @src.address_registers - \
	            1 elementof (index metadataof @src.address_registers)
	compute mask,mask or 1 shl reg
next_memory_term:
	compute index,index+1
	jump memory_term

register:
	; x86-2 marks AH/CH/DH/BH through REX_FORBIDDEN. Collapse every
	; 8/16/32/64-bit alias to one physical GPR number.
	compute reg,@src.rm
	check reg and x86.REX_FORBIDDEN
	jyes high_byte_register
	compute reg,reg and 0Fh
	jump register_ready
high_byte_register:
	compute reg,(reg and 0Fh)-4
register_ready:
	compute mask,mask or 1 shl reg

done:
	emit 2,mask
end calminstruction

calminstruction xmm_reads operand*
	local mask
	compute mask,0
	call SSE.parse_operand@src,operand
	check @src.type = 'mmreg'
	jno done
	compute mask,1 shl @src.rm
done:
	emit 2,mask
end calminstruction

gpr_reads rdx
gpr_reads [rcx+r8*4+10h]
gpr_reads 7
gpr_reads [rax+r10]
gpr_reads edx
gpr_reads dx
gpr_reads dl
gpr_reads dh
gpr_reads [rip+20h]
gpr_reads spl
gpr_reads r9b
xmm_reads xmm3
xmm_reads xmm15
xmm_reads qword [rcx+r9*4]

load .rdx_mask:2 from 0
load .address_mask:2 from 2
load .immediate_mask:2 from 4
load .scratch_mask:2 from 6
load .edx_mask:2 from 8
load .dx_mask:2 from 10
load .dl_mask:2 from 12
load .dh_mask:2 from 14
load .rip_mask:2 from 16
load .spl_mask:2 from 18
load .r9b_mask:2 from 20
load .xmm3_mask:2 from 22
load .xmm15_mask:2 from 24
load .xmm_memory_mask:2 from 26

assert .rdx_mask = 1 shl 2
assert .address_mask = (1 shl 1) or (1 shl 8)
assert .immediate_mask = 0
assert .scratch_mask = (1 shl 0) or (1 shl 10)
assert .edx_mask = 1 shl 2
assert .dx_mask = 1 shl 2
assert .dl_mask = 1 shl 2
assert .dh_mask = 1 shl 2
assert .rip_mask = 0
assert .spl_mask = 1 shl 4
assert .r9b_mask = 1 shl 9
assert .xmm3_mask = 1 shl 3
assert .xmm15_mask = 1 shl 15
assert .xmm_memory_mask = 0
