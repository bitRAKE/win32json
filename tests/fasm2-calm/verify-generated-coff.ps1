param(
    [string]$AsmGameRoot = "C:\git\!bitRAKE\asmgame",
    [string]$LlvmBin = "C:\Program Files\LLVM\bin"
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Generated = Join-Path $Repo "generated\fasm2_calm\x64"
$Source = Join-Path $PSScriptRoot "generated_coff.asm"
$Object = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-generated-coff.obj"
$Fasmg = Join-Path $AsmGameRoot "fasm2\fasmg.exe"
$Readobj = Join-Path $LlvmBin "llvm-readobj.exe"

foreach ($Path in @($Fasmg, $Readobj, $Source, $Generated)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "required test input not found: $Path"
    }
}

$PreviousInclude = $env:INCLUDE
try {
    $env:INCLUDE = "$Repo;$AsmGameRoot\include;$Generated;$AsmGameRoot\fasm2\include;$PreviousInclude"
    if (Test-Path -LiteralPath $Object) {
        Remove-Item -LiteralPath $Object
    }
    & $Fasmg "-iInclude('fasm2.inc')" -n $Source $Object
    if ($LASTEXITCODE -ne 0) {
        throw "generated COFF fixture failed: exit $LASTEXITCODE"
    }
}
finally {
    $env:INCLUDE = $PreviousInclude
}

$Relocations = (& $Readobj --relocations $Object) -join "`n"
$Symbols = (& $Readobj --symbols $Object) -join "`n"
if ($Relocations -notmatch 'IMAGE_REL_AMD64_REL32\s+CreateProcessW') {
    throw "missing COFF REL32 relocation against CreateProcessW"
}
if ($Symbols -match 'Name:\s+CreateThread') {
    throw "unused KERNEL32 external leaked into generated COFF object"
}

Write-Output "verify: generated COFF contract ok ($Object)"
