@echo off
setlocal
chcp 65001 >nul
title SoonAI CLI installer
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Install
if errorlevel 1 (
  echo [ERROR] ติดตั้งไม่สำเร็จ
  pause
  exit /b 1
)

echo.
echo Installation complete. เปิด terminal ใหม่แล้วใช้คำสั่ง: soonai
pause
