@echo off
rem English-named shortcut maker, same as 바탕화면 바로가기 만들기.bat
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title BaekSutalk Studio - create desktop shortcut

if not exist ".venv\Scripts\pythonw.exe" goto no_venv
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create-shortcut.ps1"
pause
exit /b 0

:no_venv
echo [INFO] Run the launcher once first (실행하기.bat / run.bat).
pause
exit /b 1
