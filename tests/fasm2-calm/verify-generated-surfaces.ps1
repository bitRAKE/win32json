param(
    [string]$Fasm2Root = "C:\git\fasm2"
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Generated = Join-Path $Repo "generated\fasm2_calm\x64"
$Fasmg = Join-Path $Fasm2Root "fasmg.exe"
$Include = Join-Path $Fasm2Root "include"

$PreviousInclude = $env:INCLUDE
try {
    $env:INCLUDE = "$Generated;$Repo;$Include;$PreviousInclude"
    foreach ($Name in @("downlevel", "apiset")) {
        $Source = Join-Path $PSScriptRoot "generated_${Name}_surface.asm"
        $Output = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-generated-${Name}-surface.bin"
        if (Test-Path -LiteralPath $Output) {
            Remove-Item -LiteralPath $Output
        }
        & $Fasmg "-iInclude('dd.inc')" "-iInclude('x86-2.inc')" $Source $Output
        if ($LASTEXITCODE -ne 0) {
            throw "generated $Name public surface failed: exit $LASTEXITCODE"
        }
        if ((Get-Item -LiteralPath $Output).Length -ne 1) {
            throw "generated $Name public surface emitted unexpected data"
        }
    }

    $ConflictSource = Join-Path $PSScriptRoot "generated_surface_conflict.asm"
    $ConflictOutput = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-generated-surface-conflict.bin"
    $SavedErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $ConflictLog = (& $Fasmg "-iInclude('dd.inc')" "-iInclude('x86-2.inc')" $ConflictSource $ConflictOutput 2>&1) -join "`n"
    $ConflictExitCode = $LASTEXITCODE
    $ErrorActionPreference = $SavedErrorAction
    if ($ConflictExitCode -eq 0) {
        throw "including both public function subsets unexpectedly succeeded"
    }
    if ($ConflictLog -notmatch "public Win32 function subset is already selected") {
        throw "public subset conflict did not report the expected gate diagnostic"
    }
}
finally {
    $env:INCLUDE = $PreviousInclude
}

Write-Output "verify: full generated down-level and API-set surfaces assemble"
