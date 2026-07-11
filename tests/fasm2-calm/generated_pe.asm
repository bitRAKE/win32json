; Generated public function contract routed through a used-only PE64 import.

format PE64 NX console 6.0
entry start

include 'macro/proc64.inc'
include 'generated/fasm2_calm/x64/runtime/fastcall_adapter.g'
include 'generated/fasm2_calm/x64/backends/pe/downlevel/kernel32.g'
include 'generated/fasm2_calm/x64/contracts/downlevel/qualified/kernel32.g'
include 'generated/fasm2_calm/x64/contracts/downlevel/public/kernel32.g'

section '.text' code readable executable
start:
	GetCurrentProcessId
	ret

section '.idata' import data readable writeable
include 'generated/fasm2_calm/x64/backends/pe/downlevel_imports.g'
