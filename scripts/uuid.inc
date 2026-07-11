
; UUID is a symbolic space and separate constant data space.


; create assemble-time of names/values
;	- allows type-checking of passed symbols
;	- name aliasing allowed
define UUID.IID_IUnknown 00000000-0000-0000-C000-000000000046
define UUID.IID_IClassFactory 00000001-0000-0000-C000-000000000046
define UUID.IID_IDispatch 00020400-0000-0000-C000-000000000046
define UUID.IID_AsyncIUnknown 000E0000-0000-0000-C000-000000000046

; add names to assemble-time database
;	- enables output of used data
define UUID IID_IUnknown
define UUID IID_IClassFactory
define UUID IID_IDispatch
define UUID IID_AsyncIUnknown

calminstruction UUID line&
	match ,line
	jyes empty
	match =?,line
	jyes empty
	match =< =>,line
	jyes empty
resolve:
	match { A =, B =, C =, D =, { E } }, line, {}
	jyes cform
	match { A - B - C - D - E }, line, {}
	jyes stnd
	match A - B - C - D - E, line
	jyes stnd
	; nested extraction from namespace database
	transform line,UUID
	jyes resolve
bad:	err 'unexpected UUID form'
	exit

empty:	emit 16
	exit

stnd:	arrange A, 0x#A
	arrange B, 0x#B
	arrange C, 0x#C
	arrange D, 0x#D#E
	compute D, D
	emit 4, A
	emit 2, B
	emit 2, C
	emit 8, D bswap 8
	exit

cform:	emit 4,A
	emit 2,B
	emit 2,C
	emit 2,D bswap 2
	match A =, B =, C =, D =, E =, F, E
	jno bad
	emit 1,A
	emit 1,B
	emit 1,C
	emit 1,D
	emit 1,E
	emit 1,F
end calminstruction

calminstruction(NAMED) UUID line&
	local tmp
	arrange tmp, =label NAMED:4 ; :note: only alignment of 4 required
	assemble tmp
	arrange tmp, =UUID line
	assemble tmp
end calminstruction


postpone
	irpv uuid,UUID
		if used uuid
			uuid UUID UUID.uuid
		end if
	end irpv
end postpone
