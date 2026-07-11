; NEWCOFF bigobj with automatic CodeView and unwind metadata.

include 'dd.inc'
include 'align.inc'
include 'format.inc'
include 'x86-2.inc'
use AMD64

NEWCOFF.DEBUG := 6
format MS64 NEWCOFF
include 'macro/proc64.inc'
include 'cases_calm/fixed_call64.g'

define win32.select.downlevel kernel32
include 'generated/fasm2_calm/x64/windows.inc'

prologue@proc equ newcoff_debug_prologue
epilogue@proc equ static_rsp_epilogue
close@proc equ newcoff_debug_close
newcoff_debug_procs

section '.text$start' code readable executable comdat align 16
public start
proc start
	ExitProcess ERROR_SUCCESS
endp
