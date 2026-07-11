# win32json

A JSON representation of win32metadata.

# How are these files Generated?

https://github.com/marlersoft/win32jsongen

# TODO

* create a schema

## Projections

* [`cases/README.md`](cases/README.md) exercises the standard flat fasm2
  projection in `generated/fasm2/` through direct PE, API-set PE, legacy COFF,
  and NEWCOFF final products.
* [`generated/fasm2_calm/README.md`](generated/fasm2_calm/README.md) defines
  the consolidated CALM projection; its generated x64 function/value surface
  includes gated down-level/API-set contracts plus direct PE and Microsoft
  COFF linkage backends.
* [`cases_calm/README.md`](cases_calm/README.md) separately exercises the CALM
  projection through the same binary trajectories, making the differing call
  and include surfaces explicit.
