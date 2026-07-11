param(
    [string]$Fasm2Root = "C:\git\!bitRAKE\asmgame",
    [string]$LlvmBin = "C:\Program Files\LLVM\bin"
)

$ErrorActionPreference = "Stop"
$Repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Source = Join-Path $PSScriptRoot "interface_contract.asm"
$Object = Join-Path ([System.IO.Path]::GetTempPath()) "win32json-interface-contract.obj"
$Fasmg = Join-Path $Fasm2Root "fasm2\fasmg.exe"
$Objdump = Join-Path $LlvmBin "llvm-objdump.exe"
$Readobj = Join-Path $LlvmBin "llvm-readobj.exe"

foreach ($Path in @($Fasmg, $Objdump, $Readobj, $Source)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "required test input not found: $Path"
    }
}

$PreviousInclude = $env:INCLUDE
try {
    $env:INCLUDE = "$Repo;$Fasm2Root\include;$Fasm2Root\fasm2\include;$PreviousInclude"
    if (Test-Path -LiteralPath $Object) {
        Remove-Item -LiteralPath $Object
    }
    & $Fasmg "-iInclude('fasm2.inc')" -n $Source $Object
    if ($LASTEXITCODE -ne 0) {
        throw "interface contract assembly failed: exit $LASTEXITCODE"
    }
}
finally {
    $env:INCLUDE = $PreviousInclude
}

$Disassembly = (& $Objdump -d --no-show-raw-insn $Object) -join "`n"
$Relocations = (& $Readobj --relocations $Object) -join "`n"

$Checks = @(
    @{ Name = "IUnknown Release slot"; Count = 1; Pattern = 'callq\s+\*0x10\(%rax\)' },
    @{ Name = "ITest SetMode slot"; Count = 3; Pattern = 'callq\s+\*0x18\(%rax\)' },
    @{ Name = "symbolic mode value"; Count = 2; Pattern = 'pushq\s+\$0x7' },
    @{ Name = "register bypass"; Count = 1; Pattern = 'movq\s+%r11, %rcx' }
)

foreach ($Check in $Checks) {
    $Actual = ([regex]::Matches($Disassembly, $Check.Pattern)).Count
    if ($Actual -ne $Check.Count) {
        throw "$($Check.Name): expected $($Check.Count) match(es), found $Actual"
    }
}

if ($Relocations -notmatch 'IMAGE_REL_AMD64_REL32\s+TestTarget') {
    throw "missing COFF REL32 relocation against TestTarget"
}

Write-Output "verify: interface contract ok ($Object)"
