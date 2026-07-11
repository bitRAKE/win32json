; COFF assembly linked with the installed PSDK KERNEL32 and WS2_32 libraries.

include 'dd.inc'
include 'align.inc'
include 'format.inc'
include 'x86-2.inc'
use AMD64

format MS64 COFF
include 'macro/struct.inc'
include 'macro/proc64.inc'
include 'cases/fixed_call64.g'
include 'generated/fasm2_calm/x64/types/networking_winsock/WSAData.g'
define win32.select.downlevel kernel32,ws2_32
include 'generated/fasm2_calm/x64/windows.inc'

public start
WS_VERSION_REQUIRED = 2 + (2 shl 8) ; MAKEWORD(2,2)
prologue@proc equ static_rsp_prologue
epilogue@proc equ static_rsp_epilogue
close@proc equ static_rsp_close procname

proc start
	locals
		wsa_data WSAData
	endl

	lea rax,[wsa_data]
	WSAStartup WS_VERSION_REQUIRED,rax
	test eax,eax ; zero is success; otherwise EAX is a Winsock error code
	jnz .exit
	WSACleanup
.exit:
	ExitProcess eax
endp
