param(
    [ValidateSet("x86", "x64", "arm64")]
    [string]$Arch = "x64",
    [string]$OutRoot = "generated\fasm2",
    [switch]$Clean,
    [switch]$Verify,
    [switch]$SmokeAssemble,
    [string]$Fasm2 = "C:\git\fasm2\fasmg.exe",
    [string]$Fasm2Root = "C:\git\fasm2",
    [int]$FasmTimeout = 300
)

$ErrorActionPreference = "Stop"
$Repo = Resolve-Path (Join-Path $PSScriptRoot "..")
$OutDir = Join-Path (Join-Path $Repo $OutRoot) $Arch
$Args = @(
    (Join-Path $PSScriptRoot "win32json_fasm2.py"),
    "generate",
    "--api-dir", (Join-Path $Repo "api"),
    "--arch", $Arch,
    "--out-dir", $OutDir
)
if ($Clean) { $Args += "--clean" }
if ($Verify) {
    $Args += "--verify"
    if ($SmokeAssemble) {
        if ($Fasm2) { $Args += @("--fasm2", $Fasm2) }
        if ($Fasm2Root) { $Args += @("--fasm2-root", $Fasm2Root) }
        $Args += @("--fasm-timeout", $FasmTimeout)
    }
}

python @Args
exit $LASTEXITCODE
