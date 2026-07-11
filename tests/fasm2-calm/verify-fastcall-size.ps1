param(
    [string]$Fasm2Root = "C:\git\fasm2"
)

$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "fastcall_size.asm"
$Output = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-fastcall-size.bin"
$Fasmg = Join-Path $Fasm2Root "fasmg.exe"
$Include = Join-Path $Fasm2Root "include"

foreach ($Path in @($Fasmg, $Include, $Source)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "required test input not found: $Path"
    }
}

$PreviousInclude = $env:INCLUDE
try {
    $env:INCLUDE = "$Include;$PreviousInclude"
    if (Test-Path -LiteralPath $Output) {
        Remove-Item -LiteralPath $Output
    }
    & $Fasmg "-iInclude('dd.inc')" "-iInclude('x86-2.inc')" $Source $Output
    if ($LASTEXITCODE -ne 0) {
        throw "fastcall size fixture failed: exit $LASTEXITCODE"
    }
}
finally {
    $env:INCLUDE = $PreviousInclude
}

if ((Get-Item -LiteralPath $Output).Length -ne 203) {
    throw "fastcall size fixture emitted an unexpected total length"
}

Write-Output "verify: fastcall size facts ok ($Output)"
