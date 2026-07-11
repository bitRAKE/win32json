# win32json

A JSON representation of win32metadata.

# How are these files Generated?

https://github.com/marlersoft/win32jsongen

# TODO

* create a schema

## Projections

* [`generated/fasm2_calm/README.md`](generated/fasm2_calm/README.md) defines
  the consolidated CALM projection; its generated x64 function/value surface
  includes gated down-level/API-set contracts plus direct PE and Microsoft
  COFF linkage backends.
* [`cases/README.md`](cases/README.md) exercises that projection through final
  PE products: direct assembly, PSDK/LLVM COFF linkage, import inspection, and
  execution.
