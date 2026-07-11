; Standard fasm2 projection: flat equates/pcounts and generated PE imports.

include 'generated/fasm2/x64/equates/all.inc'
format PE64 NX console 6.0
entry start

include 'macro/proc64.inc'
include 'macro/import64.inc'
include 'cases/pe_support.inc'
include 'generated/fasm2/x64/pcount/kernel32.inc'

prologue@proc equ static_rsp_prologue
epilogue@proc equ static_rsp_epilogue
close@proc equ static_rsp_close procname

section '.text' code readable executable
proc start
	fastcall [ExitProcess],ERROR_SUCCESS
endp

section '.idata' import data readable writeable
include 'generated/fasm2/x64/imports/library.inc'
include 'generated/fasm2/x64/imports/all.inc'
