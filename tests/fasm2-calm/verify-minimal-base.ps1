param(
    [string]$Fasm2Root = "C:\git\fasm2",
    [string]$LlvmBin = "C:\Program Files\LLVM\bin"
)

$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "minimal_base.asm"
$Object = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-minimal-base.obj"
$Fasmg = Join-Path $Fasm2Root "fasmg.exe"
$Readobj = Join-Path $LlvmBin "llvm-readobj.exe"

foreach ($Path in @($Fasmg, $Readobj, $Source)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "required test input not found: $Path"
    }
}

$PreviousInclude = $env:INCLUDE
try {
    $env:INCLUDE = "$(Join-Path $Fasm2Root 'include');$PreviousInclude"
    if (Test-Path -LiteralPath $Object) {
        Remove-Item -LiteralPath $Object
    }
    & $Fasmg $Source $Object
    if ($LASTEXITCODE -ne 0) {
        throw "minimal include baseline failed: exit $LASTEXITCODE"
    }
}
finally {
    $env:INCLUDE = $PreviousInclude
}

$Info = (& $Readobj --file-headers --sections --symbols $Object) -join "`n"
foreach ($Pattern in @('Format: COFF-x86-64', 'Name: .text', 'Name: .data', 'Name: minimal_base_smoke')) {
    if ($Info -notmatch [regex]::Escape($Pattern)) {
        throw "minimal include baseline is missing '$Pattern'"
    }
}

Write-Output "verify: minimal include baseline ok ($Object)"
