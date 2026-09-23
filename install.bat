@echo off
title SoonAI CLI installer
cd /d "%~dp0"
echo ============================================
echo   SoonAI CLI installer
echo ============================================

REM --- Check for PyInstaller for binary build ---
set "BUILD_BINARY=0"
where pyinstaller >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "BUILD_BINARY=1"
    echo [INFO] PyInstaller พบ — กำลังสร้าง binary (soonai.exe)…
    pyinstaller --noconfirm --clean --onefile --name soonai soonai.py
    if !ERRORLEVEL! equ 0 (
        echo [OK] Binary build เสร็จ: soonai.exe
    ) else (
        echo [WARN] Binary build ล้มเหลว — จะใช้ Python แทน
        set "BUILD_BINARY=0"
    )
) else (
    echo [INFO] ไม่พบ PyInstaller — จะติดตั้งผ่าน requirements-dev.txt
    python -m pip install pyinstaller
    if !ERRORLEVEL! equ 0 (
        pyinstaller --noconfirm --clean --onefile --name soonai soonai.py
        if !ERRORLEVEL! equ 0 (
            echo [OK] Binary build เสร็จ: soonai.exe
            set "BUILD_BINARY=1"
        ) else (
            echo [WARN] Binary build ล้มเหลว — จะใช้ Python แทน
            set "BUILD_BINARY=0"
        )
    ) else (
        echo [WARN] ติดตั้ง PyInstaller ไม่สำเร็จ — ใช้ Python แทน
        set "BUILD_BINARY=0"
    )
)

REM --- Install dependencies ---
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed. Is Python installed?
  pause
  exit /b 1
)

REM --- Choose install location ---
set "TARGET_DIR=%LOCALAPPDATA%\SoonAI"
echo Installing to: %TARGET_DIR%

REM --- Copy only distributable files. Never copy keys, sessions, caches, logs or temp files. ---
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
if not exist "%TARGET_DIR%\shared" mkdir "%TARGET_DIR%\shared"
REM --- Copy bundled binary ถ้าสร้างสำเร็จ ---
if %BUILD_BINARY% equ 1 (
    if exist "%~dp0dist\soonai.exe" (
        copy /Y "%~dp0dist\soonai.exe" "%TARGET_DIR%\soonai.exe" >nul
        echo [OK] Copy soonai.exe ไปยัง %TARGET_DIR%
    )
)
for %%F in (soonai.py soonai.bat soonoi.bat install.bat install.ps1 requirements.txt) do copy /Y "%~dp0%%F" "%TARGET_DIR%\%%F" >nul
REM --- Copy ALL shared modules (ห้ามระบุรายไฟล์ เดี๋ยวตกหล่นแบบเดิมอีก) ---
copy /Y "%~dp0shared\*.py" "%TARGET_DIR%\shared\" >nul
if not exist "%TARGET_DIR%\shared\config.json" copy /Y "%~dp0shared\config.json" "%TARGET_DIR%\shared\config.json" >nul
if not exist "%TARGET_DIR%\shared\team.json" copy /Y "%~dp0shared\team.json" "%TARGET_DIR%\shared\team.json" >nul
if not exist "%TARGET_DIR%\shared\mcp.json" copy /Y "%~dp0shared\mcp.json" "%TARGET_DIR%\shared\mcp.json" >nul

REM --- Copy bundled skills (ถ้ามี) ---
if exist "%~dp0shared\skills\*" xcopy /E /I /Y "%~dp0shared\skills" "%TARGET_DIR%\shared\skills" >nul

REM --- Create launcher in target dir (เก็บ UTF-8/py-fallback แบบ soonai.bat) ---
(
echo @echo off
echo chcp 65001 ^>nul
echo set PYTHONIOENCODING=utf-8
echo set PYTHONUTF8=1
REM --- ถ้ามี .exe ให้รัน .exe ก่อน ไม่งั้นใช้ Python ---
if exist "%TARGET_DIR%\soonai.exe" (
    echo "%TARGET_DIR%\soonai.exe" %%*
) else (
echo where python ^>nul 2^>nul
echo if errorlevel 1 ^(
echo   py "%TARGET_DIR%\soonai.py" %%*
echo ^) else ^(
echo   python "%TARGET_DIR%\soonai.py" %%*
echo ^)
)
) > "%TARGET_DIR%\soonai.bat"

REM --- Add to User PATH permanently (ไม่ต้องใช้สิทธิ์ admin) ---
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -TargetDir "%TARGET_DIR%"
if errorlevel 1 (
  echo [WARN] เพิ่ม PATH อัตโนมัติไม่สำเร็จ — เพิ่มเองได้ที่:
  echo        %TARGET_DIR%
) else (
  echo [OK] เพิ่ม %TARGET_DIR% ลง User PATH แล้ว
)

echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo รันได้:
echo   soonai              → เปิดห้องแชท
echo   soonai providers    → ดูผู้ให้บริการ
echo   soonai models       → ดูโมเดล
echo   soonai skills       → จัดการ skills
echo   soonai test         → รันเทสต์อัตโนมัติ
echo   soonai git status   → ดูสถานะ git
echo.
pause
