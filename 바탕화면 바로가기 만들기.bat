@echo off
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"
title 백수톡 스튜디오 - 바탕화면 바로가기 만들기
color 0B

echo ==========================================================
echo    백수톡 스튜디오 - 바탕화면 바로가기 만들기
echo ==========================================================
echo.

if not exist "launcher.py" goto no_files
if not exist "assets\app.ico" goto no_icon

if not exist ".venv\Scripts\pythonw.exe" goto no_venv

echo 바탕화면에 '백수톡 스튜디오' 아이콘을 만드는 중...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create-shortcut.ps1"
if errorlevel 1 goto ps_fail
echo.
echo 완료! 바탕화면의 '백수톡 스튜디오'를 더블클릭하면
echo 까만 창 없이 앱 창으로 바로 열립니다.
echo.
pause
exit /b 0

:no_files
echo [문제] launcher.py 를 찾을 수 없습니다.
echo        ZIP 압축을 푼 폴더 안에서 실행해 주세요.
pause
exit /b 1

:no_icon
echo [문제] assets\app.ico 가 없습니다. ZIP 을 다시 받아 주세요.
pause
exit /b 1

:no_venv
echo [안내] 먼저 실행하기.bat 을 한 번 실행해 주세요.
echo        (처음 준비가 끝나면 이 파일을 다시 더블클릭하면 됩니다)
echo.
pause
exit /b 1

:ps_fail
echo.
echo [문제] 바로가기를 만들지 못했습니다.
echo        Windows 보안 설정이 PowerShell 을 막고 있을 수 있어요.
echo        폴더 안의 create-shortcut.ps1 을 직접 실행해도 됩니다.
echo.
pause
exit /b 1
