; Prototype interface surface. Requires scripts/fastcall.g and, for the
; focused routing fixture, the historical COM-aware fastcall macro it adapts.
; Production calls retain the same win32.fastcall entry point but use the
; register-retirement scheduler.

define win32.COM ; searchable interface method registry

; allowed {iid} forms: (named pointer to 16 bytes of data)
;	{0x03020100,0x0504,0x0706,0x0809,{0x0a,0x0b,0x0c,0x0d,0x0e,0x0f}}
;	{03020100-0504-0706-0809-0a0b0c0d0e0f}
;	03020100-0504-0706-0809-0a0b0c0d0e0f
;	extrn "<name>"
;	...
; interface vtbl offsets for manual use:
;	fastcall.params [.irich]
;	mov rax, [rcx]
;	call [rax + IUnknown__Release]
;
; interface vtbl macros for terse use:
;	IUnknown__Release [.irich]
;
; interface object macro for most-terse use:
;	.irich IUnknown
;	.irich->Release

macro interface? IFACE*,extends,iid*,methods&
	local functions

	; Public namespace for interface-local aliases, constants and enums.
	; Generated declarations may populate children without adding global names:
	;       define win32.IFACE.ENUM.VALUE 1
	define win32.IFACE.base extends
	define win32.IFACE.iid iid

	if used IID_#IFACE
		define GUID.IID_#IFACE iid ; add to database
		{const:16} IID_#IFACE GUID iid
	end if

	match ,extends
		functions equ methods
	else match ,methods
		functions equ win32.COM.extends
	else
		functions equ win32.COM.extends,methods
	end match
	win32.COM.IFACE equ functions
	define win32.IFACE.methods functions

	match funcs,functions
	iterate func,funcs
		label IFACE#__#func:qword at %*8-8

		; Generic fallback. A generated parameter contract can redefine this
		; instruction with exact formals and type-namespace transforms while
		; retaining the same win32.fastcall target.
		calminstruction IFACE#__#func object*,&arguments&
			local line
			match ,arguments
			jyes no_arguments
			arrange line, =win32.fastcall {%*8-8},object,arguments
			assemble line
			exit
		no_arguments:
			arrange line, =win32.fastcall {%*8-8},object
			assemble line
		end calminstruction
	end iterate
	end match

	struc(POBJECT) IFACE
		POBJECT rq 1
		; Assemble-time-only storage tag. Registers intentionally bypass it.
		define POBJECT.__win32_type IFACE
		; prevent look-ahead infinite loop
		calminstruction POBJECT
		end calminstruction
		calminstruction POBJECT line*&
			local iface,pobj,function
			initsym iface,IFACE#__
			initsym pobj,POBJECT

			match =-=> function= line,line
			jyes gop
			match =-=> function,line
			jyes go
			; why forward? err 'misuse of ',`POBJECT
			arrange line,pobj line
			assemble line
			exit

		go:	arrange line,iface#function [pobj]
; by-pass function interface:
;			arrange line,=fastcall {iface#function},[pobj]
			assemble line
			exit

		gop:	arrange line,iface#function [pobj],line
			assemble line
		end calminstruction
	end struc
end macro
