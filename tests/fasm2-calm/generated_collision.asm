; Explicit raw-name selection for the sole x64 function/function collision.

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
include 'generated/fasm2_calm/x64/backends/recording/downlevel/dsound.g'
include 'generated/fasm2_calm/x64/backends/recording/downlevel/tbs.g'
include 'generated/fasm2_calm/x64/contracts/downlevel/qualified/tbs.g'

; This gate selects the DSOUND meaning for the otherwise withheld raw name.
include 'generated/fasm2_calm/x64/contracts/downlevel/collisions/GetDeviceID_dsound.g'

.selected_dsound:
	GetDeviceID 1,2
.selected_dsound_end:

.qualified_tbs:
	win32.api.tbs.GetDeviceID 1,2,3,4
.qualified_tbs_end:

assert .selected_dsound_end - .selected_dsound = 21
assert .qualified_tbs_end - .qualified_tbs = 37

load .dsound_target:4 from .selected_dsound
load .dsound_count:1 from .selected_dsound + 4
load .tbs_target:4 from .qualified_tbs
load .tbs_count:1 from .qualified_tbs + 4

assert .dsound_target <> .tbs_target
assert .dsound_count = 2
assert .tbs_count = 4
