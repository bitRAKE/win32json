; Curated baseline: fasmg core + selected fasm2 components, not fasm2.inc.

include 'dd.inc'
include 'align.inc'
include 'format.inc'
include 'x86-2.inc'
use AMD64

format MS64 COFF
include 'macro/struct.inc'

; These names remain ordinary symbols because the legacy helpers that own
; them were not included.
fix = 11
times = 12
invoke = 13
addr = 14
assert fix + times + invoke + addr = 50

struct MINIMAL_RECORD
	value dd ?
	align 8
	pointer dq ?
ends

section '.text' code readable executable align 16
public minimal_base_smoke
minimal_base_smoke:
	xor eax,eax
	ret

section '.data' data readable writeable align 8
minimal_record MINIMAL_RECORD
assert sizeof MINIMAL_RECORD = 16
