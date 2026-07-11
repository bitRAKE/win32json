; Direct PE64 assembly through the concrete/down-level projection.

include 'dd.inc'
include 'align.inc'
include 'format.inc'
include 'x86-2.inc'
use AMD64

format PE64 NX console 6.0
entry start

include 'macro/proc64.inc'
include 'cases/fixed_call64.g'
define win32.select.downlevel kernel32
include 'generated/fasm2_calm/x64/windows.inc'

prologue@proc equ static_rsp_prologue
epilogue@proc equ static_rsp_epilogue
close@proc equ static_rsp_close procname

section '.text' code readable executable
proc start
	ExitProcess ERROR_SUCCESS
endp
