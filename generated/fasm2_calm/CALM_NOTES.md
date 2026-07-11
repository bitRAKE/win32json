ARRANGE glues pieces of tokenized text together and stores this text in a symbolic variable. You can arrange pieces in such way that it forms new identifiers, but ARRANGE does not require the text you produce to have any meaning, it is up to you to use the value of this variable for chosen purpose later.

For example, TRANSFORM would take the text contained in this variable and look for identifiers of other symbolic variables to replace each of them with its content (and each has a value containing tokenized source text, since this is what "symbolic variable" is in fasm) and put this final unrolled text into the same variable. Here your newly constructed identifier (like one with appended index) would get recognized.

As for COMPUTE, normally it does not deal with tokenized text at all, it computes a pre-compiled expression and stores the numeric (not symbolic) result in a variable. Only if the pre-compiled expression uses a variable that happens to have a symbolic value, COMPUTE parses this text as a new sub-expression and then evaluates it. This is obviously slower, as it requires additional parsing, while the main expression for the COMPUTE has been already parsed at the time when the instruction was compiled (that is: during the definition of CALM instruction).

However this means that if you construct an indexed identifier and put it into a variable that is accessed by pre-compiled expression of COMPUTE, it is going to be parsed and evaluated as a sub-expression, and thus it can also access a symbol with newly synthesised name.

And, of course, the target variable of ARRANGE, TRANSFORM, COMPUTE is always just a pre-compiled reference to a symbol, so it is static, already decided at the time when the instruction is defined.

The target of a CALL is also a static reference to a symbol, in this case an instruction-class symbol. You can still alter the value of such symbol, by redefining a macro, or with MVMACRO/PURGE. However in case of JUMP/JYES/JNO the target is doubly static, because it is compiled into an internal reference to a specific position inside CALM bytecode. Once the instruction is compiled, this target cannot be changed in any way.

## Anchoring dotted namespaces for `TRANSFORM`

Defining only leaves in a dotted namespace does not make every intermediate
namespace a searchable symbolic node. For example, these definitions alone are
not sufficient for `transform value,win32.BOOL` to resolve the short token
`FALSE`:

```asm
define win32.BOOL.FALSE 0
define win32.BOOL.TRUE 1
```

Anchor every namespace level that is going to be passed to `TRANSFORM`. A
circular definition intentionally creates the node without giving it a
different spelling:

```asm
define win32 win32
define win32.BOOL win32.BOOL
define win32.BOOL.FALSE 0
define win32.BOOL.TRUE 1

calminstruction emit_bool value*
        transform value,win32.BOOL
        arrange value,=db value
        assemble value
end calminstruction

emit_bool FALSE             ; emits 0
emit_bool TRUE              ; emits 1
emit_bool win32.BOOL.FALSE  ; the fully qualified spelling also remains valid
```

Both anchors matter when neither node existed previously: anchoring
`win32.BOOL` while leaving `win32` unanchored is insufficient. The same rule
applies recursively to deeper transform scopes.

For generated Win32 enums, emit the root anchor once and one anchor per enum:

```asm
define win32 win32
define win32.PROCESS_CREATION_FLAGS win32.PROCESS_CREATION_FLAGS
define win32.PROCESS_CREATION_FLAGS.CREATE_NEW_CONSOLE 10h
```

Generated contracts should then use the public namespace directly:

```asm
transform dwCreationFlags,win32.PROCESS_CREATION_FLAGS
```

Do not introduce a flattened duplicate such as `win32__PROCESS_CREATION_FLAGS`
merely to make `TRANSFORM` work. It creates two value trees that can diverge and
hides the missing anchor. The focused regression fixture is
`tests/fasm2-calm/namespace_anchor.asm`.
