; Generated public function contract routed through Microsoft x64 COFF.

include 'windows.g'
include 'generated/fasm2_calm/x64/windows.g'
include 'generated/fasm2_calm/x64/backends/coff/downlevel/kernel32.g'
include 'generated/fasm2_calm/x64/contracts/downlevel/qualified/kernel32.g'
include 'generated/fasm2_calm/x64/contracts/downlevel/public/kernel32.g'

public generated_coff_smoke
generated_coff_smoke:
	CreateProcessW ,,,,FALSE,CREATE_NEW_CONSOLE,,,0,0
	ret
