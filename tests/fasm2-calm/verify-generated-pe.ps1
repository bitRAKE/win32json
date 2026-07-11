param(
    [string]$Fasm2Root = "C:\git\fasm2",
    [string]$LlvmBin = "C:\Program Files\LLVM\bin"
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Generated = Join-Path $Repo "generated\fasm2_calm\x64"
$Source = Join-Path $PSScriptRoot "generated_pe.asm"
$Image = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-generated-pe.exe"
$Fasmg = Join-Path $Fasm2Root "fasmg.exe"
$Readobj = Join-Path $LlvmBin "llvm-readobj.exe"

foreach ($Path in @($Fasmg, $Readobj, $Source, $Generated)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "required test input not found: $Path"
    }
}

$PreviousInclude = $env:INCLUDE
try {
    $env:INCLUDE = "$Generated;$Repo;$Fasm2Root\include;$PreviousInclude"
    if (Test-Path -LiteralPath $Image) {
        Remove-Item -LiteralPath $Image
    }
    & $Fasmg "-iInclude('fasm2.inc')" $Source $Image
    if ($LASTEXITCODE -ne 0) {
        throw "generated PE fixture failed: exit $LASTEXITCODE"
    }
}
finally {
    $env:INCLUDE = $PreviousInclude
}

$Imports = (& $Readobj --coff-imports $Image) -join "`n"
if ($Imports -notmatch 'Name:\s+KERNEL32\.dll') {
    throw "generated PE is missing KERNEL32.dll"
}
if ($Imports -notmatch 'Symbol:\s+GetCurrentProcessId') {
    throw "generated PE is missing GetCurrentProcessId"
}
if ($Imports -match 'CreateProcessW') {
    throw "unused CreateProcessW import leaked into generated PE"
}

Write-Output "verify: generated used-only PE import ok ($Image)"
