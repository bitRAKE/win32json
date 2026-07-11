; Direct PE64 assembly using an API-set contract and its public enum namespace.

include 'dd.inc'
include 'align.inc'
include 'format.inc'
include 'x86-2.inc'
use AMD64

format PE64 NX console 6.0
entry start

include 'macro/proc64.inc'
include 'cases_calm/fixed_call64.g'
define win32.select.apisets api_ms_win_core_winrt_l1_1_0
include 'generated/fasm2_calm/x64/windows.inc'

prologue@proc equ static_rsp_prologue
epilogue@proc equ static_rsp_epilogue
close@proc equ static_rsp_close procname

section '.text' code readable executable
proc start
	RoInitialize RO_INIT_MULTITHREADED
	test eax,eax
	js .done
	RoUninitialize
	xor eax,eax
.done:
	ret
endp
