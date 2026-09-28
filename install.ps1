# SoonAI CLI installer for Windows.
# Installs into the current user's LocalAppData and updates the user PATH.
#
# โฟลเดอร์ปลายทางเป็นตำแหน่งเดียวกับ DATA_DIR ของโปรแกรม (runtime.data_dir())
# ซึ่งเก็บ sessions/audit.log/config.json/keys.json อยู่แล้ว — ตั้งใจให้เป็นเช่นนั้น
# installer จึงห้ามเขียนทับไฟล์ข้อมูลเหล่านั้น (ดู $excludeNames ด้านล่าง)
[CmdletBinding()]
param(
    [string]$TargetDir = (Join-Path $env:LOCALAPPDATA "SoonAI"),
    [switch]$Install,
    [string]$Source = "local"
)

$ErrorActionPreference = "Stop"
$sourceDir = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$target = [System.IO.Path]::GetFullPath($TargetDir).TrimEnd('\')
$venvDir = Join-Path $target ".venv"

function Get-PythonCandidates {
    $candidates = @()
    foreach ($cmd in @("py", "python", "python3")) {
        $resolved = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($resolved) {
            $candidates += @{ Exe = $resolved.Source; Args = @() }
            if ($cmd -eq "py") {
                $candidates += @{ Exe = $resolved.Source; Args = @("-3") }
            }
        }
    }

    $commonRoots = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "$env:USERPROFILE\AppData\Local\Programs\Python",
        "$env:ProgramFiles\Python",
        "$env:ProgramFiles(x86)\Python"
    )
    foreach ($root in $commonRoots) {
        if (Test-Path $root) {
            foreach ($exe in (Get-ChildItem -Path $root -Recurse -Filter python.exe -File -ErrorAction SilentlyContinue)) {
                $candidates += @{ Exe = $exe.FullName; Args = @() }
            }
        }
    }
    return $candidates
}

function Get-PythonVersionMetric {
    param([string]$Exe, [string[]]$Args)
    try {
        $out = & $Exe @Args -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $text = ($out | Out-String).Trim()
            if ($text -match '^\d+\.\d+$') {
                return [version]$text
            }
        }
    } catch {
        return $null
    }
    return $null
}

function Get-PythonCommand {
    foreach ($candidate in (Get-PythonCandidates)) {
        $version = Get-PythonVersionMetric -Exe $candidate.Exe -Args $candidate.Args
        if ($version) {
            return @{ Exe = $candidate.Exe; Args = $candidate.Args; Version = $version }
        }
    }
    throw "Python 3.12+ was not found. Automatic installer will try to install it."
}

function Ensure-PythonAvailable {
    try {
        $resolved = Get-PythonCommand
        if ($resolved.Version -ge [version]"3.12") {
            return $resolved
        }
    } catch {
        Write-Host "[INFO] Python 3.12+ was not found on this machine."
    }

    $os = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    Write-Host "[INFO] Detected OS: $os"

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "[INFO] Auto-installing Python 3.12 via winget for Windows..."
        & winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "Automatic Python install via winget failed. Please install Python 3.12+ manually."
        }
        $retry = Get-PythonCommand
        if ($retry.Version -lt [version]"3.12") {
            throw "Python was installed but version is below 3.12. Please install Python 3.12+ manually."
        }
        return $retry
    }

    throw "Python 3.12+ was not found and winget is unavailable. Install Python 3.12+ manually from https://www.python.org/downloads/windows/"
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

# ของที่ห้ามคัดลอกตามไปยังเครื่องอื่น:
#   keys.json/config.json/team.json/mcp.json = ความลับกับค่าส่วนตัวของผู้พัฒนา
#     (ของจริงอยู่ที่ DATA_DIR ซึ่งบน Windows คือโฟลเดอร์ปลายทางเดียวกันนี้ — ไม่ต้องมีร่างซ้ำใน shared/)
#   .machine_id/.models_cache.json/__pycache__ = ของที่เครื่องปลายทางสร้างเองได้
$excludeNames = @("keys.json", "config.json", "team.json", "mcp.json",
                  ".machine_id", ".models_cache.json")

function Copy-TreeFiltered([string]$From, [string]$To) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    $fromFull = [System.IO.Path]::GetFullPath($From).TrimEnd('\')
    Get-ChildItem -LiteralPath $fromFull -Recurse -Force -File | ForEach-Object {
        $relative = $_.FullName.Substring($fromFull.Length).TrimStart('\').Replace('/', '\')
        if ($excludeNames -contains $_.Name) { return }
        # เทียบ __pycache__ เป็นชื่อโฟลเดอร์ตรง ๆ (ไม่ใช้ regex — หนีบ backslash ใน PowerShell สะดุดง่าย)
        if ($relative.StartsWith('__pycache__\') -or $relative.Contains('\__pycache__\')) { return }
        $destination = Join-Path $To $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
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

$sourceName = ($Source ?? "local").ToLowerInvariant()
if ($sourceName -in @("github", "git", "remote")) {
    Write-Host "[INFO] GitHub/remote source detected. Using the local installer flow for this machine."
    $Source = "local"
}

$python = Ensure-PythonAvailable
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

$files = @("soonai.py", "requirements.txt", "soonai.spec", "README.md")
foreach ($file in $files) {
    Copy-Item -LiteralPath (Join-Path $sourceDir $file) -Destination $target -Force
}
Copy-TreeFiltered (Join-Path $sourceDir "shared") (Join-Path $target "shared")

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
