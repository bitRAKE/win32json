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

## Regenerating the projections

Run these commands from the repository root. The standard generator supports
`x86`, `x64`, and `arm64`; replace both architecture occurrences together when
selecting another target.

```sh
python scripts/win32json_fasm2.py generate --api-dir api --arch x64 --out-dir generated/fasm2/x64 --clean --verify
python scripts/win32json_fasm2.py verify --api-dir api --arch x64 --out-dir generated/fasm2/x64
```

The PowerShell wrappers provide the same standard generation and verification
entry points:

```powershell
./scripts/build-fasm2-api.ps1 -Arch x64 -Clean -Verify
./scripts/verify-fasm2-api.ps1 -Arch x64
```

Verification checks the generated file set, symbol uniqueness, references,
GUID coverage, and import partitioning. Add `--fasm2 <path>` and
`--fasm2-root <checkout>` to either Python command (or `-SmokeAssemble` to the
PowerShell wrappers) to also assemble the smoke sources.

The consolidated CALM generator currently supports `x64`:

```sh
python scripts/win32json_fasm2_calm.py generate --api-dir api --arch x64 --out-dir generated/fasm2_calm/x64 --clean
python scripts/win32json_fasm2_calm.py verify --api-dir api --arch x64 --out-dir generated/fasm2_calm/x64
```
