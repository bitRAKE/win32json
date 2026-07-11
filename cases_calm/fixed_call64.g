; Focused fixed-frame lowering for the CALM projection usage cases.
;
; The caller must reserve and align a complete Win64 frame. This provider never
; changes RSP. It deliberately accepts only the immediate/register forms used
; by the current cases; the production dependency scheduler will replace it.

; proc64.inc installs the historical mover under the transformed `fastcall`
; instruction name. Remove that macro while retaining its proc/frame state.
purge fastcall
macro fastcall target*,arguments&
	local value
	if fastcall?.frame < 0
		err 'fixed_call64.g requires a static_rsp proc frame'
	else if fastcall?.frame < 20h
		fastcall?.frame = 20h
	end if
	iterate argument,arguments
		if % > 2
			err 'fixed_call64.g only supports the first two register arguments'
		end if

		value reequ argument
		x86.parse_operand@src argument
		if @src.type = 'imm'
			if ~ (value) relativeto 0
				err 'fixed_call64.g does not accept relocatable argument identities'
			else if value < 0 | value > 0FFFFFFFFh
				err 'fixed_call64.g immediate is outside its supported UInt32 range'
			else if % = 1
				if value = 0
					xor ecx,ecx
				else
					mov ecx,value
				end if
			else
				if value = 0
					xor edx,edx
				else
					mov edx,value
				end if
			end if
		else if @src.type = 'reg'
			if @src.size = 8
				if % = 1
					mov rcx,value
				else
					mov rdx,value
				end if
			else if @src.size = 4
				if % = 1
					mov ecx,value
				else
					mov edx,value
				end if
			else
				err 'fixed_call64.g only accepts 32-bit and 64-bit register sources'
			end if
		else
			err 'fixed_call64.g only accepts immediate and register sources'
		end if
	end iterate
	call target
end macro
