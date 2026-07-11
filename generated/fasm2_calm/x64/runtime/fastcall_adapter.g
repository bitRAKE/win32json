; Generated runtime protocol adapter.
; The final Win64 scheduler may replace this implementation while retaining
; the win32.fastcall target-and-operand-list interface.

namespace win32

        define linkage

        calminstruction fastcall target*,&arguments&
                local line,slot

                match {slot},target
                jyes lower
                transform target,linkage

        lower:
                match ,arguments
                jyes no_arguments
                arrange line,=fastcall target,arguments
                assemble line
                exit

        no_arguments:
                arrange line,=fastcall target
                assemble line
        end calminstruction

end namespace
