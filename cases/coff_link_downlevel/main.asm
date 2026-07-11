; Standard fasm2 projection: complete declarations in a legacy COFF object.

include 'generated/fasm2/x64/equates/all.inc'
format MS64 COFF
include 'macro/struct.inc'
include 'macro/proc64.inc'
include 'generated/fasm2/x64/types/selective/networking_winsock/WSAData.inc'
include 'generated/fasm2/x64/pcount/kernel32.inc'
include 'generated/fasm2/x64/pcount/ws2_32.inc'

extrn ExitProcess
extrn WSACleanup
extrn WSAStartup

prologue@proc equ static_rsp_prologue
epilogue@proc equ static_rsp_epilogue
close@proc equ static_rsp_close procname

WS_VERSION_REQUIRED = 2 + (2 shl 8) ; MAKEWORD(2,2)

section '.text$s' code readable executable align 16
public start
proc start
	locals
		wsa_data WSAData
	endl
	lea rax,[wsa_data]
	fastcall WSAStartup,WS_VERSION_REQUIRED,rax
	test eax,eax
	jnz .exit
	fastcall WSACleanup
.exit:
	fastcall ExitProcess,eax
endp
