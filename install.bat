@echo off
setlocal
chcp 65001 >nul
title SoonAI CLI installer
cd /d "%~dp0"

where winget >nul 2>nul
if not errorlevel 1 (
  powershell -NoProfile -Command "Write-Host '[INFO] Detected OS: Windows'; if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command python3 -ErrorAction SilentlyContinue)) { Write-Host '[INFO] Python 3.12+ was not found. Installing automatically...'; winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements; if ($LASTEXITCODE -ne 0) { exit 1 } }"
  if errorlevel 1 (
    echo [ERROR] ไม่สามารถติดตั้ง Python 3.12+ ให้เองได้
    echo [INFO] กรุณาติดตั้งจาก https://www.python.org/downloads/windows/ หรือรัน: winget install --id Python.Python.3.12 -e
    pause
    exit /b 1
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Install
if errorlevel 1 (
  echo [ERROR] ติดตั้งไม่สำเร็จ
  pause
  exit /b 1
)

echo.
echo Installation complete. เปิด terminal ใหม่แล้วใช้คำสั่ง: soonai
pause
