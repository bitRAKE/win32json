param(
    [string]$Fasm2Root = "C:\git\fasm2",
    [string]$LlvmBin = "C:\Program Files\LLVM\bin",
    [string]$WindowsSdkLib,
    [switch]$NoRun
)

$ErrorActionPreference = "Stop"
$Cases = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Cases "..")).Path
$Generated = Join-Path $Repo "generated\fasm2\x64"
$Out = Join-Path $Cases "out"
$Fasmg = Join-Path $Fasm2Root "fasmg.exe"
$Readobj = Join-Path $LlvmBin "llvm-readobj.exe"
$Objdump = Join-Path $LlvmBin "llvm-objdump.exe"
$Link = Join-Path $LlvmBin "lld-link.exe"

if (-not $WindowsSdkLib) {
    $WindowsSdkLib = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\Lib" -Directory -ErrorAction Stop |
        Where-Object { $_.Name -match '^\d+(\.\d+)+$' -and (Test-Path (Join-Path $_.FullName "um\x64\kernel32.lib")) } |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if ($WindowsSdkLib) {
        $WindowsSdkLib = Join-Path $WindowsSdkLib "um\x64"
    }
}

foreach ($Path in @($Fasmg, $Readobj, $Objdump, $Link, $Generated,
    (Join-Path $WindowsSdkLib "kernel32.lib"), (Join-Path $WindowsSdkLib "ws2_32.lib"))) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        throw "required case input not found: $Path"
    }
}
New-Item -ItemType Directory -Force $Out | Out-Null

function Invoke-Assembly {
    param([string]$Source, [string]$Output)
    $PreviousInclude = $env:INCLUDE
    try {
        $env:INCLUDE = "$Repo;$Generated;$Fasm2Root\include;$PreviousInclude"
        Remove-Item -LiteralPath $Output -Force -ErrorAction SilentlyContinue
        & $Fasmg "-iInclude('fasm2.inc')" -n $Source $Output
        if ($LASTEXITCODE -ne 0) { throw "fasmg failed for $Source with exit code $LASTEXITCODE" }
    }
    finally { $env:INCLUDE = $PreviousInclude }
}

function Assert-Match {
    param([string]$Text, [string]$Pattern, [string]$Message)
    if ($Text -notmatch $Pattern) { throw $Message }
}

function Get-ImageInfo {
    param([string]$Image)
    $Text = (& $Readobj --file-headers --sections --coff-imports --unwind $Image) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "llvm-readobj failed for $Image" }
    return $Text
}

function Assert-StaticFrame {
    param([string]$Image, [int]$MinimumSize = 32)
    $Text = (& $Objdump -d $Image) -join "`n"
    $Matches = [regex]::Matches($Text, 'subq\s+\$0x([0-9a-fA-F]+),\s*%rsp')
    if ($Matches.Count -ne 1) { throw "$Image must contain exactly one static RSP subtraction" }
    $Size = [Convert]::ToInt32($Matches[0].Groups[1].Value, 16)
    if ($Size -lt $MinimumSize -or ($Size % 16) -ne 8) { throw "$Image has invalid Win64 frame size $Size" }
    return $Text
}

function Invoke-Product {
    param([string]$Image, [int]$ExpectedExitCode)
    if ($NoRun) { return }
    $Process = Start-Process -FilePath $Image -Wait -PassThru -NoNewWindow
    if ($Process.ExitCode -ne $ExpectedExitCode) { throw "$Image exited with $($Process.ExitCode), expected $ExpectedExitCode" }
}

function Link-Object {
    param([string]$Object, [string]$Image, [string[]]$Libraries)
    Remove-Item -LiteralPath $Image -Force -ErrorAction SilentlyContinue
    & $Link "/entry:start" "/subsystem:console" "/machine:x64" "/nodefaultlib" "/out:$Image" $Object $Libraries
    if ($LASTEXITCODE -ne 0) { throw "lld-link failed for $Object" }
}

$Direct = Join-Path $Out "direct_pe_downlevel.exe"
Invoke-Assembly (Join-Path $Cases "direct_pe_downlevel\main.asm") $Direct
$Info = Get-ImageInfo $Direct
Assert-Match $Info 'Name:\s+KERNEL32\.dll' "regular direct PE is missing KERNEL32.dll"
Assert-Match $Info 'Symbol:\s+ExitProcess' "regular direct PE is missing ExitProcess"
if ($Info -match 'CreateProcessW') { throw "unused regular import leaked into direct PE" }
$Info | Set-Content -Encoding utf8 (Join-Path $Out "direct_pe_downlevel.readobj.txt")
(Assert-StaticFrame $Direct) | Set-Content -Encoding utf8 (Join-Path $Out "direct_pe_downlevel.objdump.txt")
Invoke-Product $Direct 0
Write-Output "case: regular fasm2 direct PE ok ($Direct)"

$ApiSet = Join-Path $Out "direct_pe_apiset.exe"
Invoke-Assembly (Join-Path $Cases "direct_pe_apiset\main.asm") $ApiSet
$Info = Get-ImageInfo $ApiSet
foreach ($Pattern in @('Name:\s+api-ms-win-core-winrt-l1-1-0\.dll', 'Symbol:\s+RoInitialize', 'Symbol:\s+RoUninitialize')) {
    Assert-Match $Info $Pattern "regular API-set PE is missing evidence matching $Pattern"
}
$Info | Set-Content -Encoding utf8 (Join-Path $Out "direct_pe_apiset.readobj.txt")
(Assert-StaticFrame $ApiSet) | Set-Content -Encoding utf8 (Join-Path $Out "direct_pe_apiset.objdump.txt")
Invoke-Product $ApiSet 0
Write-Output "case: regular fasm2 API-set PE ok ($ApiSet)"

$CoffObject = Join-Path $Out "coff_link_downlevel.obj"
$CoffImage = Join-Path $Out "coff_link_downlevel.exe"
Invoke-Assembly (Join-Path $Cases "coff_link_downlevel\main.asm") $CoffObject
$ObjectInfo = (& $Readobj --file-headers --relocations --symbols $CoffObject) -join "`n"
foreach ($Symbol in @('WSAStartup','WSACleanup','ExitProcess')) {
    Assert-Match $ObjectInfo "IMAGE_REL_AMD64_REL32\s+$Symbol" "regular COFF object lacks $Symbol relocation"
}
$ObjectInfo | Set-Content -Encoding utf8 (Join-Path $Out "coff_link_downlevel.object.readobj.txt")
Link-Object $CoffObject $CoffImage @((Join-Path $WindowsSdkLib "kernel32.lib"),(Join-Path $WindowsSdkLib "ws2_32.lib"))
$Info = Get-ImageInfo $CoffImage
foreach ($Pattern in @('Name:\s+KERNEL32\.dll','Symbol:\s+ExitProcess','Name:\s+WS2_32\.dll','Symbol:\s+\(115\)','Symbol:\s+\(116\)')) {
    Assert-Match $Info $Pattern "regular linked COFF image lacks evidence matching $Pattern"
}
$Info | Set-Content -Encoding utf8 (Join-Path $Out "coff_link_downlevel.image.readobj.txt")
(Assert-StaticFrame $CoffImage 440) | Set-Content -Encoding utf8 (Join-Path $Out "coff_link_downlevel.objdump.txt")
Invoke-Product $CoffImage 0
Write-Output "case: regular fasm2 COFF + declarations + PSDK ok ($CoffImage)"

$NewObject = Join-Path $Out "newcoff_link_downlevel.obj"
$NewImage = Join-Path $Out "newcoff_link_downlevel.exe"
Invoke-Assembly (Join-Path $Cases "newcoff_link_downlevel\main.asm") $NewObject
$Bytes = [System.IO.File]::ReadAllBytes($NewObject)
if ($Bytes.Count -lt 56 -or $Bytes[0] -ne 0 -or $Bytes[1] -ne 0 -or $Bytes[2] -ne 0xFF -or $Bytes[3] -ne 0xFF) {
    throw "regular NEWCOFF object lacks the bigobj signature"
}
$ObjectInfo = (& $Readobj --file-headers --sections --relocations --symbols --codeview --unwind $NewObject) -join "`n"
foreach ($Pattern in @('IMAGE_REL_AMD64_REL32\s+ExitProcess','Name:\s+\.debug\$S','Name:\s+\.pdata','Name:\s+\.xdata','GlobalProcSym','ALLOC_SMALL size=40')) {
    Assert-Match $ObjectInfo $Pattern "regular NEWCOFF object lacks evidence matching $Pattern"
}
$ObjectInfo | Set-Content -Encoding utf8 (Join-Path $Out "newcoff_link_downlevel.object.readobj.txt")
Link-Object $NewObject $NewImage @((Join-Path $WindowsSdkLib "kernel32.lib"))
$Info = Get-ImageInfo $NewImage
Assert-Match $Info 'Symbol:\s+ExitProcess' "regular NEWCOFF image lacks ExitProcess"
Assert-Match $Info 'ALLOC_SMALL size=40' "regular NEWCOFF image lacks unwind information"
$Info | Set-Content -Encoding utf8 (Join-Path $Out "newcoff_link_downlevel.image.readobj.txt")
(Assert-StaticFrame $NewImage) | Set-Content -Encoding utf8 (Join-Path $Out "newcoff_link_downlevel.objdump.txt")
Invoke-Product $NewImage 0
Write-Output "case: regular fasm2 NEWCOFF + CodeView/unwind + PSDK ok ($NewImage)"

Write-Output "all standard fasm2 projection cases passed; CALM cases are under cases_calm"
