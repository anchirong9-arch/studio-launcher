@echo off
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"
title 통합 스튜디오 - 서버 끄기
color 0C

echo ==========================================================
echo    통합 스튜디오 - 켜 둔 서버 정리
echo ==========================================================
echo.

set "PYRUN="
if exist ".venv\Scripts\python.exe" set "PYRUN=.venv\Scripts\python.exe"
if not defined PYRUN goto try_py
goto do_stop

:try_py
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys" >nul 2>nul
if errorlevel 1 goto try_python
set "PYRUN=py -3"
goto do_stop

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
set "PYRUN=python"

:do_stop
if not exist "launcher.py" goto no_files
%PYRUN% launcher.py --stop
echo.
pause
exit /b 0

:no_files
echo [문제] launcher.py 를 찾을 수 없습니다. 압축을 푼 폴더에서 실행해 주세요.
pause
exit /b 1

:no_python
echo [안내] Python 을 찾지 못했습니다. 서버는 작업 관리자에서 python 을 끝내 주세요.
pause
exit /b 1
