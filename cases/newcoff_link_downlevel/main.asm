; Standard fasm2 projection: NEWCOFF with generated equates and pcounts.

include 'generated/fasm2/x64/equates/all.inc'
NEWCOFF.DEBUG := 6
format MS64 NEWCOFF
include 'macro/proc64.inc'
include 'generated/fasm2/x64/pcount/kernel32.inc'

extrn ExitProcess

prologue@proc equ newcoff_debug_prologue
epilogue@proc equ static_rsp_epilogue
close@proc equ newcoff_debug_close
newcoff_debug_procs

section '.text$start' code readable executable comdat align 16
public start
proc start
	fastcall ExitProcess,ERROR_SUCCESS
endp
