param(
    [string]$Fasm2Root = "C:\git\fasm2",
    [string]$LlvmBin = "C:\Program Files\LLVM\bin",
    [string]$WindowsSdkLib,
    [switch]$NoRun
)

$ErrorActionPreference = "Stop"
$Cases = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Cases "..")).Path
$Generated = Join-Path $Repo "generated\fasm2_calm\x64"
$Out = Join-Path $Cases "out"
$Fasm2 = Join-Path $Fasm2Root "fasmg.exe"
$Readobj = Join-Path $LlvmBin "llvm-readobj.exe"
$Objdump = Join-Path $LlvmBin "llvm-objdump.exe"
$Link = Join-Path $LlvmBin "lld-link.exe"

if (-not $WindowsSdkLib) {
    $SdkRoot = "C:\Program Files (x86)\Windows Kits\10\Lib"
    $WindowsSdkLib = Get-ChildItem $SdkRoot -Directory -ErrorAction Stop |
        Where-Object { $_.Name -match '^\d+(\.\d+)+$' -and (Test-Path (Join-Path $_.FullName "um\x64\kernel32.lib")) } |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if ($WindowsSdkLib) {
        $WindowsSdkLib = Join-Path $WindowsSdkLib "um\x64"
    }
}

$Required = @(
    $Fasm2,
    $Readobj,
    $Objdump,
    $Link,
    (Join-Path $WindowsSdkLib "kernel32.lib"),
    (Join-Path $WindowsSdkLib "ws2_32.lib")
)
foreach ($Path in $Required) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        throw "required case input not found: $Path"
    }
}

New-Item -ItemType Directory -Force $Out | Out-Null

function Invoke-Fasmg {
    param(
        [string]$Assembler,
        [string]$Source,
        [string]$Output,
        [string]$IncludePath
    )

    $PreviousInclude = $env:INCLUDE
    try {
        $env:INCLUDE = "$IncludePath;$PreviousInclude"
        Remove-Item -LiteralPath $Output -Force -ErrorAction SilentlyContinue
        & $Assembler -n $Source $Output
        if ($LASTEXITCODE -ne 0) {
            throw "fasmg failed for $Source with exit code $LASTEXITCODE"
        }
    }
    finally {
        $env:INCLUDE = $PreviousInclude
    }
}

function Get-ReadobjText {
    param([string]$Image)
    $Text = (& $Readobj --file-headers --sections --coff-imports $Image) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "llvm-readobj failed for $Image"
    }
    return $Text
}

function Assert-Match {
    param([string]$Text, [string]$Pattern, [string]$Message)
    if ($Text -notmatch $Pattern) {
        throw $Message
    }
}

function Invoke-Product {
    param([string]$Image, [int]$ExpectedExitCode)
    if ($NoRun) {
        return
    }
    $Process = Start-Process -FilePath $Image -Wait -PassThru -NoNewWindow
    if ($Process.ExitCode -ne $ExpectedExitCode) {
        throw "$Image exited with $($Process.ExitCode), expected $ExpectedExitCode"
    }
}

function Assert-StaticFrame {
    param([string]$Image, [int]$MinimumSize = 32)

    $Disassembly = (& $Objdump -d $Image) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "llvm-objdump failed for $Image"
    }
    $Matches = [regex]::Matches($Disassembly, 'subq\s+\$0x([0-9a-fA-F]+),\s*%rsp')
    if ($Matches.Count -ne 1) {
        throw "$Image must contain exactly one static RSP subtraction; found $($Matches.Count)"
    }
    $FrameSize = [Convert]::ToInt32($Matches[0].Groups[1].Value, 16)
    if ($FrameSize -lt $MinimumSize) {
        throw "$Image frame is $FrameSize bytes, below required $MinimumSize"
    }
    if (($FrameSize % 16) -ne 8) {
        throw "$Image frame is $FrameSize bytes, expected a size congruent to 8 modulo 16"
    }
    return $Disassembly
}

$Direct = Join-Path $Out "direct_pe_downlevel.exe"
Invoke-Fasmg `
    -Assembler $Fasm2 `
    -Source (Join-Path $Cases "direct_pe_downlevel\main.asm") `
    -Output $Direct `
    -IncludePath "$Generated;$Repo;$Fasm2Root\include"
$DirectInfo = Get-ReadobjText $Direct
Assert-Match $DirectInfo 'Format: COFF-x86-64' "direct PE is not x64"
Assert-Match $DirectInfo 'Name:\s+KERNEL32\.dll' "direct PE is missing KERNEL32.dll"
Assert-Match $DirectInfo 'Symbol:\s+ExitProcess' "direct PE is missing ExitProcess"
if ($DirectInfo -match 'GetCurrentProcessId') {
    throw "unused KERNEL32 import leaked into direct PE"
}
$DirectInfo | Set-Content -Encoding utf8 (Join-Path $Out "direct_pe_downlevel.readobj.txt")
$DirectDisassembly = Assert-StaticFrame $Direct
$DirectDisassembly | Set-Content -Encoding utf8 (Join-Path $Out "direct_pe_downlevel.objdump.txt")
Invoke-Product $Direct 0
Write-Output "case: direct PE down-level projection ok ($Direct)"

$Object = Join-Path $Out "coff_link_downlevel.obj"
$Linked = Join-Path $Out "coff_link_downlevel.exe"
Invoke-Fasmg `
    -Assembler $Fasm2 `
    -Source (Join-Path $Cases "coff_link_downlevel\main.asm") `
    -Output $Object `
    -IncludePath "$Generated;$Repo;$Fasm2Root\include"
$ObjectInfo = (& $Readobj --file-headers --relocations --symbols $Object) -join "`n"
foreach ($Symbol in @('WSAStartup', 'WSACleanup', 'ExitProcess')) {
    Assert-Match $ObjectInfo "IMAGE_REL_AMD64_REL32\s+$Symbol" "COFF object is missing relocation for $Symbol"
}
$ObjectInfo | Set-Content -Encoding utf8 (Join-Path $Out "coff_link_downlevel.object.readobj.txt")

Remove-Item -LiteralPath $Linked -Force -ErrorAction SilentlyContinue
& $Link "/entry:start" "/subsystem:console" "/machine:x64" "/nodefaultlib" "/out:$Linked" `
    $Object (Join-Path $WindowsSdkLib "kernel32.lib") (Join-Path $WindowsSdkLib "ws2_32.lib")
if ($LASTEXITCODE -ne 0) {
    throw "lld-link failed with exit code $LASTEXITCODE"
}
$LinkedInfo = Get-ReadobjText $Linked
foreach ($Pattern in @('Name:\s+KERNEL32\.dll', 'Symbol:\s+ExitProcess', 'Name:\s+WS2_32\.dll', 'Symbol:\s+\(115\)', 'Symbol:\s+\(116\)')) {
    Assert-Match $LinkedInfo $Pattern "linked PSDK image is missing import matching $Pattern"
}
$LinkedInfo | Set-Content -Encoding utf8 (Join-Path $Out "coff_link_downlevel.image.readobj.txt")
$LinkedDisassembly = Assert-StaticFrame $Linked (32 + 408)
$LinkedDisassembly | Set-Content -Encoding utf8 (Join-Path $Out "coff_link_downlevel.objdump.txt")
Invoke-Product $Linked 0
Write-Output "case: COFF + PSDK linkage projection ok ($Linked)"

$NewObject = Join-Path $Out "newcoff_link_downlevel.obj"
$NewLinked = Join-Path $Out "newcoff_link_downlevel.exe"
Invoke-Fasmg `
    -Assembler $Fasm2 `
    -Source (Join-Path $Cases "newcoff_link_downlevel\main.asm") `
    -Output $NewObject `
    -IncludePath "$Generated;$Repo;$Fasm2Root\include"
$NewBytes = [System.IO.File]::ReadAllBytes($NewObject)
if ($NewBytes.Count -lt 56 -or $NewBytes[0] -ne 0 -or $NewBytes[1] -ne 0 -or $NewBytes[2] -ne 0xFF -or $NewBytes[3] -ne 0xFF) {
    throw "NEWCOFF object is missing the ANON_OBJECT_HEADER_BIGOBJ signature"
}
$NewObjectInfo = (& $Readobj --file-headers --sections --relocations --symbols --codeview --unwind $NewObject) -join "`n"
if ($LASTEXITCODE -ne 0) {
    throw "llvm-readobj failed for NEWCOFF object"
}
foreach ($Pattern in @(
    'Format:\s+COFF-x86-64',
    'Machine:\s+IMAGE_FILE_MACHINE_AMD64',
    'Name:\s+\.debug\$S',
    'Name:\s+\.pdata',
    'Name:\s+\.xdata',
    'IMAGE_REL_AMD64_REL32\s+ExitProcess',
    'GlobalProcSym',
    'TotalFrameBytes:\s+0x28',
    'ALLOC_SMALL size=40'
)) {
    Assert-Match $NewObjectInfo $Pattern "NEWCOFF object is missing evidence matching $Pattern"
}
$NewObjectInfo | Set-Content -Encoding utf8 (Join-Path $Out "newcoff_link_downlevel.object.readobj.txt")

Remove-Item -LiteralPath $NewLinked -Force -ErrorAction SilentlyContinue
& $Link "/entry:start" "/subsystem:console" "/machine:x64" "/nodefaultlib" "/out:$NewLinked" `
    $NewObject (Join-Path $WindowsSdkLib "kernel32.lib")
if ($LASTEXITCODE -ne 0) {
    throw "lld-link failed for NEWCOFF with exit code $LASTEXITCODE"
}
$NewLinkedInfo = (& $Readobj --file-headers --sections --coff-imports --unwind $NewLinked) -join "`n"
foreach ($Pattern in @('Name:\s+KERNEL32\.dll', 'Symbol:\s+ExitProcess', 'ALLOC_SMALL size=40')) {
    Assert-Match $NewLinkedInfo $Pattern "linked NEWCOFF image is missing evidence matching $Pattern"
}
$NewLinkedInfo | Set-Content -Encoding utf8 (Join-Path $Out "newcoff_link_downlevel.image.readobj.txt")
$NewDisassembly = Assert-StaticFrame $NewLinked
$NewDisassembly | Set-Content -Encoding utf8 (Join-Path $Out "newcoff_link_downlevel.objdump.txt")
Invoke-Product $NewLinked 0
Write-Output "case: NEWCOFF bigobj + CodeView/unwind + PSDK linkage ok ($NewLinked)"

$ApiSet = Join-Path $Out "direct_pe_apiset.exe"
Invoke-Fasmg `
    -Assembler $Fasm2 `
    -Source (Join-Path $Cases "direct_pe_apiset\main.asm") `
    -Output $ApiSet `
    -IncludePath "$Generated;$Repo;$Fasm2Root\include"
$ApiSetInfo = Get-ReadobjText $ApiSet
Assert-Match $ApiSetInfo 'Name:\s+api-ms-win-core-winrt-l1-1-0\.dll' "API-set PE is missing its contract DLL"
Assert-Match $ApiSetInfo 'Symbol:\s+RoInitialize' "API-set PE is missing RoInitialize"
Assert-Match $ApiSetInfo 'Symbol:\s+RoUninitialize' "API-set PE is missing RoUninitialize"
if ($ApiSetInfo -match 'RoActivateInstance') {
    throw "unused API-set import leaked into direct PE"
}
$ApiSetInfo | Set-Content -Encoding utf8 (Join-Path $Out "direct_pe_apiset.readobj.txt")
$ApiSetDisassembly = Assert-StaticFrame $ApiSet
$ApiSetDisassembly | Set-Content -Encoding utf8 (Join-Path $Out "direct_pe_apiset.objdump.txt")
Invoke-Product $ApiSet 0
Write-Output "case: direct PE API-set projection ok ($ApiSet)"

Write-Output "all CALM projection usage cases passed; Windows SDK libraries: $WindowsSdkLib"
