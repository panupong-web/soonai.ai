# SoonAI CLI installer for Windows.
# Installs into the current user's LocalAppData and updates the user PATH.
[CmdletBinding()]
param(
    [string]$TargetDir = (Join-Path $env:LOCALAPPDATA "SoonAI"),
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$sourceDir = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$target = [System.IO.Path]::GetFullPath($TargetDir).TrimEnd('\')
$venvDir = Join-Path $target ".venv"

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @{ Exe = $py.Source; Args = @("-3") } }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @{ Exe = $python.Source; Args = @() } }
    throw "Python 3 was not found. Install it from https://www.python.org/downloads/windows/"
}

function Add-UserPath([string]$PathToAdd) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    $parts = @($userPath -split ';' | Where-Object { $_ -and $_.Trim() -ne "" })
    foreach ($part in $parts) {
        if ($part.TrimEnd('\') -ieq $PathToAdd.TrimEnd('\')) {
            Write-Host "[OK] $PathToAdd is already in the user PATH"
            return
        }
    }
    [Environment]::SetEnvironmentVariable("Path", ((@($parts) + $PathToAdd) -join ';'), "User")
    Write-Host "[OK] Added $PathToAdd to the user PATH"
}

function Assert-Success([string]$Operation) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

if (-not $Install) {
    if (-not (Test-Path -LiteralPath $target)) {
        Write-Host "[ERROR] Install directory does not exist: $target"
        exit 1
    }
    Add-UserPath $target
    exit 0
}

$python = Get-PythonCommand
$pythonVersion = (& $python.Exe @($python.Args) -c "import sys; print('%s.%s' % (sys.version_info[0], sys.version_info[1]) )").Trim()
Assert-Success "Python version check"
if ($pythonVersion -notmatch '^3\.(1[2-9]|[2-9][0-9])$') {
    throw "SoonAI requires Python 3.12 or newer (found $pythonVersion)"
}
New-Item -ItemType Directory -Force -Path $target | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $venvDir "Scripts\python.exe"))) {
    & $python.Exe @($python.Args) -m venv $venvDir
    Assert-Success "Virtual environment creation"
}
$venvPython = Join-Path $venvDir "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
Assert-Success "pip upgrade"
& $venvPython -m pip install -r (Join-Path $sourceDir "requirements.txt")
Assert-Success "dependency installation"

$files = @("soonai.py", "soonai_custom.py", "requirements.txt", "soonai.spec", "README.md")
foreach ($file in $files) {
    Copy-Item -LiteralPath (Join-Path $sourceDir $file) -Destination $target -Force
}
foreach ($directory in @("shared", "apps", "packages")) {
    $destination = Join-Path $target $directory
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Copy-Item -Path (Join-Path $sourceDir "$directory\*") -Destination $destination -Recurse -Force
}

$launcher = Join-Path $target "soonai.bat"
@"
@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"$venvPython" "$target\soonai.py" %*
"@ | Set-Content -LiteralPath $launcher -Encoding ASCII

Add-UserPath $target
Write-Host ""
Write-Host "[OK] SoonAI installed to $target"
Write-Host "[INFO] Open a new terminal and run: soonai"
