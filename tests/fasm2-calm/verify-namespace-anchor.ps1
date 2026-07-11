param(
    [string]$Fasm2Root = "C:\git\fasm2"
)

$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "namespace_anchor.asm"
$Output = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-namespace-anchor.bin"
$Fasmg = Join-Path $Fasm2Root "fasmg.exe"

if (Test-Path -LiteralPath $Output) {
    Remove-Item -LiteralPath $Output
}
& $Fasmg $Source $Output
if ($LASTEXITCODE -ne 0) {
    throw "namespace anchor fixture failed: exit $LASTEXITCODE"
}

$Bytes = [System.IO.File]::ReadAllBytes($Output)
if ($Bytes.Count -ne 4 -or $Bytes[0] -ne 0 -or $Bytes[1] -ne 1 -or $Bytes[2] -ne 0 -or $Bytes[3] -ne 1) {
    throw "namespace anchor fixture emitted unexpected bytes"
}

Write-Output "verify: dotted CALM transform namespace anchor ok ($Output)"
