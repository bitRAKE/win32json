; Standard fasm2 projection: API-set pcounts and generated import tables.

include 'generated/fasm2/x64/equates/all.inc'
format PE64 NX console 6.0
entry start

include 'macro/proc64.inc'
include 'macro/import64.inc'
include 'cases/pe_support.inc'
include 'generated/fasm2/x64/pcount/api_ms_win_core_winrt_l1_1_0.inc'

prologue@proc equ static_rsp_prologue
epilogue@proc equ static_rsp_epilogue
close@proc equ static_rsp_close procname

section '.text' code readable executable
proc start
	fastcall [RoInitialize],RO_INIT_MULTITHREADED
	test eax,eax
	js .done
	fastcall [RoUninitialize]
	xor eax,eax
.done:
	ret
endp

section '.idata' import data readable writeable
include 'generated/fasm2/x64/imports/apisets_library.inc'
include 'generated/fasm2/x64/imports/apisets.inc'
