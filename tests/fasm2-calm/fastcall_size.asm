; Byte-size facts used by the Win64 call-boundary optimizer design.
; This is intentionally instruction-level: policy decides when substitutions
; are legal, while x86-2.inc remains responsible for final encodings.

format binary
use AMD64
use64

; Register argument 1 (RCX/ECX).
.mov_rcx_zero:
	mov rcx,0
assert $ - .mov_rcx_zero = 7

.xor_ecx_zero:
	xor ecx,ecx
assert $ - .xor_ecx_zero = 2

.mov_rcx_small:
	mov rcx,7
assert $ - .mov_rcx_small = 7

.push_pop_rcx_small:
	push 7
	pop rcx
assert $ - .push_pop_rcx_small = 3

; Extended ABI register argument 3 (R8/R8D).
.mov_r8_zero:
	mov r8,0
assert $ - .mov_r8_zero = 7

.xor_r8d_zero:
	xor r8d,r8d
assert $ - .xor_r8d_zero = 3

.mov_r8_small:
	mov r8,7
assert $ - .mov_r8_small = 7

.push_pop_r8_small:
	push 7
	pop r8
assert $ - .push_pop_r8_small = 4

; Fifth argument slot. The call frame has already been allocated, and 20h is
; the first stack-argument offset after Win64 shadow space.
.mov_stack_zero:
	mov qword [rsp+20h],0
assert $ - .mov_stack_zero = 9

.and_stack_zero:
	and qword [rsp+20h],0
assert $ - .and_stack_zero = 6

.mov_stack_minus_one:
	mov qword [rsp+20h],-1
assert $ - .mov_stack_minus_one = 9

.or_stack_minus_one:
	or qword [rsp+20h],-1
assert $ - .or_stack_minus_one = 6

.mov_stack_small:
	mov qword [rsp+20h],7
assert $ - .mov_stack_small = 9

.push_pop_stack_small:
	push 7
	pop qword [rsp+20h]
assert $ - .push_pop_stack_small = 6

; x86-2 already selects the sign-extended imm32 form for a qword register.
.mov_rcx_simm32:
	mov rcx,7FFFFFFFh
assert $ - .mov_rcx_simm32 = 7

; A non-negative 32-bit value can use a zero-extending dword destination with
; exactly the same 64-bit result. Current x86-2 does not select this form.
.mov_rcx_uimm32:
	mov rcx,0FFFFFFFFh
assert $ - .mov_rcx_uimm32 = 10

.mov_ecx_uimm32:
	mov ecx,0FFFFFFFFh
assert $ - .mov_ecx_uimm32 = 5

; Pure register permutations use XCHG. A narrow logical value may use a
; wider operation when only its low bits are defined.
.xchg_rcx_rdx:
	xchg rcx,rdx
assert $ - .xchg_rcx_rdx = 3

.xchg_ecx_edx:
	xchg ecx,edx
assert $ - .xchg_ecx_edx = 2

.xchg_cx_dx:
	xchg cx,dx
assert $ - .xchg_cx_dx = 3

.xchg_cl_dl:
	xchg cl,dl
assert $ - .xchg_cl_dl = 2

; Accumulator forms are recorded as x86 encoding facts. RAX/EAX is not a
; Win64 argument destination, so these are not call-scheduler pivot candidates.
.xchg_eax_ecx:
	xchg eax,ecx
assert $ - .xchg_eax_ecx = 1

.xchg_rax_rcx:
	xchg rax,rcx
assert $ - .xchg_rax_rcx = 2

.xchg_r8d_r9d:
	xchg r8d,r9d
assert $ - .xchg_r8d_r9d = 3

.xchg_r8w_r9w:
	xchg r8w,r9w
assert $ - .xchg_r8w_r9w = 4

; A three-register cycle needs two register exchanges and no temporary.
.xchg_three_cycle:
	xchg ecx,edx
	xchg edx,r8d
assert $ - .xchg_three_cycle = 5

; WORD-to-DWORD promotion removes the 66h operand-size prefix. The low 16
; bits retain the same value; the remaining bits of the ABI container are
; deliberately unspecified.
.mov_cx_dx:
	mov cx,dx
assert $ - .mov_cx_dx = 3

.mov_ecx_edx_promoted:
	mov ecx,edx
assert $ - .mov_ecx_edx_promoted = 2

.mov_rcx_rdx_full_width:
	mov rcx,rdx
assert $ - .mov_rcx_rdx_full_width = 3

; SIL needs a REX prefix in a byte operation. Reading the same low value
; through ESI makes a BYTE parameter's promoted move one byte shorter.
.mov_cl_sil:
	mov cl,sil
assert $ - .mov_cl_sil = 3

.mov_ecx_esi_promoted:
	mov ecx,esi
assert $ - .mov_ecx_esi_promoted = 2

.mov_r8w_r9w:
	mov r8w,r9w
assert $ - .mov_r8w_r9w = 4

.mov_r8d_r9d_promoted:
	mov r8d,r9d
assert $ - .mov_r8d_r9d_promoted = 3

; The same promotion saves one byte when storing a register into an outgoing
; argument slot. It does not authorize reading a wider source object.
.mov_stack_r8w:
	mov word [rsp+20h],r8w
assert $ - .mov_stack_r8w = 6

.mov_stack_r8d_promoted:
	mov dword [rsp+20h],r8d
assert $ - .mov_stack_r8d_promoted = 5

.mov_stack_sil:
	mov byte [rsp+20h],sil
assert $ - .mov_stack_sil = 5

.mov_stack_esi_promoted:
	mov dword [rsp+20h],esi
assert $ - .mov_stack_esi_promoted = 4

; Immediate representatives may differ above the parameter's defined width.
; FFFFh and -1 are the same WORD value, making the full-register push/pop form
; shorter when its separate stack/unwind permissions are available.
.mov_cx_word_minus_one:
	mov cx,0FFFFh
assert $ - .mov_cx_word_minus_one = 4

.push_pop_rcx_word_minus_one:
	push -1
	pop rcx
assert $ - .push_pop_rcx_word_minus_one = 3

; A sign-extended imm8 representative must match all defined low bits, not
; merely the low byte.
assert ((-128) and 0FFh) = 080h
assert ((-128) and 0FFFFh) = 0FF80h
assert ((-128) and 0FFFFh) <> 00080h

; Private outgoing slots can likewise use a wider RMW operation when flags
; and normal stack memory are available. Only the low WORD is defined.
.mov_stack_word_zero:
	mov word [rsp+20h],0
assert $ - .mov_stack_word_zero = 7

.and_stack_dword_zero:
	and dword [rsp+20h],0
assert $ - .and_stack_dword_zero = 5

.mov_stack_word_minus_one:
	mov word [rsp+20h],0FFFFh
assert $ - .mov_stack_word_minus_one = 7

.or_stack_dword_minus_one:
	or dword [rsp+20h],-1
assert $ - .or_stack_dword_minus_one = 5
