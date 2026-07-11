param(
    [string]$Fasm2Root = "C:\git\fasm2"
)

$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "generated_collision.asm"
$Output = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-generated-collision.bin"
$Fasmg = Join-Path $Fasm2Root "fasmg.exe"
$Include = Join-Path $Fasm2Root "include"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Generated = Join-Path $Repo "generated\fasm2_calm\x64"

$PreviousInclude = $env:INCLUDE
try {
    $env:INCLUDE = "$Generated;$Repo;$Include;$PreviousInclude"
    if (Test-Path -LiteralPath $Output) {
        Remove-Item -LiteralPath $Output
    }
    & $Fasmg "-iInclude('dd.inc')" "-iInclude('x86-2.inc')" $Source $Output
    if ($LASTEXITCODE -ne 0) {
        throw "generated collision fixture failed: exit $LASTEXITCODE"
    }
}
finally {
    $env:INCLUDE = $PreviousInclude
}

if ((Get-Item -LiteralPath $Output).Length -ne 58) {
    throw "generated collision fixture emitted an unexpected length"
}

$Report = Join-Path $Repo "generated\fasm2_calm\x64\meta\function_collisions.tsv"
$Rows = Import-Csv -Delimiter "`t" -LiteralPath $Report
$GetDeviceId = @($Rows | Where-Object { $_.function -eq "GetDeviceID" })
if ($GetDeviceId.Count -ne 2) {
    throw "expected exactly two GetDeviceID collision rows"
}

Write-Output "verify: generated collision gates ok ($Output)"
