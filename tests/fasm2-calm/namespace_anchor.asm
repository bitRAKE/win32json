; A dotted namespace must have its own node for CALM transform lookup.

format binary

define win32 win32
define win32.BOOL win32.BOOL
define win32.BOOL.FALSE 0
define win32.BOOL.TRUE 1

calminstruction emit_bool value*
	transform value,win32.BOOL
	arrange value,=db value
	assemble value
end calminstruction

emit_bool FALSE
emit_bool TRUE
emit_bool win32.BOOL.FALSE
emit_bool win32.BOOL.TRUE

assert $ = 4
