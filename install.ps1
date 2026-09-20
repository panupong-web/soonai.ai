# SoonAI CLI - add the install folder to the current user's PATH (no admin needed).
# Called by install.bat:  powershell -NoProfile -File install.ps1 -TargetDir "%LOCALAPPDATA%\SoonAI"
param(
    [Parameter(Mandatory = $true)][string]$TargetDir
)

$ErrorActionPreference = "Stop"

try {
    $target = [System.IO.Path]::GetFullPath($TargetDir).TrimEnd('\')
} catch {
    Write-Host "[ERROR] TargetDir ไม่ถูกต้อง: $TargetDir"
    exit 1
}

if (-not (Test-Path -LiteralPath $target)) {
    Write-Host "[ERROR] ไม่พบโฟลเดอร์ติดตั้ง: $target"
    exit 1
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$parts = @($userPath -split ';' | Where-Object { $_ -and $_.Trim() -ne "" })

$already = $false
foreach ($p in $parts) {
    if ($p.TrimEnd('\') -ieq $target) { $already = $true; break }
}

if ($already) {
    Write-Host "[OK] $target อยู่ใน User PATH แล้ว"
} else {
    $newPath = (@($parts) + $target) -join ';'
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "[OK] เพิ่ม $target ลง User PATH แล้ว"
}

exit 0
