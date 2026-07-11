param(
    [string]$Fasm2Root = "C:\git\fasm2"
)

$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "operand_reads.asm"
$Output = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-operand-reads.bin"
$Fasmg = Join-Path $Fasm2Root "fasmg.exe"

$PreviousInclude = $env:INCLUDE
try {
    $env:INCLUDE = "$(Join-Path $Fasm2Root 'include');$PreviousInclude"
    if (Test-Path -LiteralPath $Output) {
        Remove-Item -LiteralPath $Output
    }
    & $Fasmg "-iInclude('x86-2.inc')" $Source $Output
    if ($LASTEXITCODE -ne 0) {
        throw "operand read-set fixture failed: exit $LASTEXITCODE"
    }
}
finally {
    $env:INCLUDE = $PreviousInclude
}

if ((Get-Item -LiteralPath $Output).Length -ne 28) {
    throw "operand read-set fixture emitted an unexpected length"
}

Write-Output "verify: operand GPR/XMM read sets ok ($Output)"
