@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
where python >nul 2>nul
if errorlevel 1 (
  py "%~dp0soonai.py" %*
) else (
  python "%~dp0soonai.py" %*
)
if errorlevel 1 pause
