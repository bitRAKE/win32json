; End-to-end generated contract test using the recording linkage backend.

format binary
use AMD64
use64

macro fastcall? target*,arguments&
	local count
	count = 0
	iterate argument,arguments
		count = count + 1
	end iterate
	dd target
	db count
	iterate argument,arguments
		dq argument
	end iterate
end macro

include 'generated/fasm2_calm/x64/windows.g'
include 'generated/fasm2_calm/x64/backends/recording/downlevel/kernel32.g'
include 'generated/fasm2_calm/x64/contracts/downlevel/qualified/kernel32.g'
include 'generated/fasm2_calm/x64/contracts/downlevel/public/kernel32.g'

.public_call:
	CreateProcessW ,,,,FALSE,CREATE_NEW_CONSOLE,,,0,0
.public_call_end:

.qualified_call:
	win32.api.kernel32.CreateProcessW \
		,,,,win32.BOOL.FALSE,\
		win32.PROCESS_CREATION_FLAGS.CREATE_NEW_CONSOLE,,,0,0
.qualified_call_end:

assert .public_call_end - .public_call = 85
assert .qualified_call_end - .qualified_call = 85

load .public_target:4 from .public_call
load .public_count:1 from .public_call + 4
load .public_optional_1:8 from .public_call + 5
load .public_bool:8 from .public_call + 5 + 4*8
load .public_flags:8 from .public_call + 5 + 5*8
load .public_required_10:8 from .public_call + 5 + 9*8

load .qualified_target:4 from .qualified_call
load .qualified_count:1 from .qualified_call + 4
load .qualified_flags:8 from .qualified_call + 5 + 5*8

assert .public_target = .qualified_target
assert .public_count = 10
assert .qualified_count = 10
assert .public_optional_1 = 0
assert .public_bool = 0
assert .public_flags = 10h
assert .qualified_flags = 10h
assert .public_required_10 = 0
