; Standard fasm2 import alias hook without loading stock Win32 equates.
macro api names&
	iterate name,names
		if used name
			label name:qword at name#A
		end if
	end iterate
end macro
