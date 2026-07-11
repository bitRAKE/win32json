; Focused acceptance fixture for scripts/fastcall.g + scripts/combase.g.
; Assemble with C:\git\!bitRAKE\asmgame\fasm2.cmd and this repository on
; INCLUDE. The surrounding windows.g supplies the COM-aware fastcall macro.

include 'windows.g'
include 'scripts/fastcall.g'
include 'scripts/combase.g'

interface IUnknown,,00000000-0000-0000-C000-000000000046,\
	QueryInterface,AddRef,Release
interface ITest,IUnknown,11111111-2222-3333-4444-555555555555,\
	SetMode

; The public interface namespace holds values without global MODE_DEFAULT.
; A flat internal alias is used only for CALM namespace transformation.
define win32.ITest.MODE.DEFAULT 7
define win32__ITest__MODE
define win32__ITest__MODE.DEFAULT 7
assert win32.ITest.MODE.DEFAULT = 7

extrn TestTarget
define win32.linkage.TestTargetIdentity TestTarget

calminstruction ProjectedCall value*
	local target,arguments
	initsym target,TestTargetIdentity
	arrange arguments,value
	call win32.fastcall,target,arguments
end calminstruction

; A generated exact contract replaces the generic method fallback.
calminstruction ITest__SetMode object*,mode*
	local target,arguments
	initsym target,{ITest__SetMode}
	transform mode,win32__ITest__MODE
	arrange arguments,object,mode
	call win32.fastcall,target,arguments
end calminstruction

public interface_contract_smoke
interface_contract_smoke:
	virtual at rsp
		.object ITest
	end virtual

	; Generic inherited wrapper, exact wrapper, and object-arrow routing.
	ITest__Release [.object]
	ITest__SetMode [.object],DEFAULT
	.object->SetMode win32.ITest.MODE.DEFAULT

	; Registers are deliberately accepted without symbolic/type checks.
	ITest__SetMode [.object],r10d

	; Ordinary calls use the same adapter and backend linkage resolver.
	ProjectedCall r11
	ret

; The object struc exposes an assemble-time tag without changing storage.
match =ITest,.object.__win32_type
else
	err 'missing or incorrect interface storage tag'
end match
