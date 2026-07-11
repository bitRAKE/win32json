; Transitional backend-neutral CALM adapter for the existing COM-aware
; fastcall macro.
;
; This file proves the contract/linkage/COM routing surface only. The wrapped
; historical macro lowers operands destructively from left to right and is not
; the production implementation. The replacement keeps this public
; win32.fastcall signature but sends the complete operand list through the
; pre-scan/register-retirement scheduler before emitting any assignments.
;
; A backend may map a canonical function identity to its concrete call target:
;
;       define win32.linkage.CreateProcessW CreateProcessW       ; COFF
;       define win32.linkage.CreateProcessW [CreateProcessW]     ; direct PE
;
; COM targets use the existing {vtable-offset} form and bypass linkage lookup.

namespace win32

	define linkage

	calminstruction fastcall target*,&arguments&
		local line,slot

		match {slot},target
		jyes lower
		transform target,linkage

	lower:
		match ,arguments
		jyes no_arguments
		arrange line,=fastcall target,arguments
		assemble line
		exit

	no_arguments:
		arrange line,=fastcall target
		assemble line
	end calminstruction

end namespace
