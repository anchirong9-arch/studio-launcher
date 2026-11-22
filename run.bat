@echo off
rem English-named launcher, same as 실행하기.bat in case the Korean filename is mangled.
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"
title BaekSutalk Studio - TTS / Shorts / Coupas / Video Cut
color 0B

echo ==========================================================
echo    BaekSutalk Studio - TTS / Shorts / Coupas / Video Cut
echo ==========================================================
echo.

if not exist "launcher.py" goto no_files

set "PYEXE="
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys" >nul 2>nul
if errorlevel 1 goto try_python
set "PYEXE=py -3"
goto python_ready

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
set "PYEXE=python"

:python_ready
%PYEXE% -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul
if errorlevel 1 goto old_python

if exist ".venv\Scripts\python.exe" goto have_venv
echo [1/3] First run only. This takes 1-3 minutes.
echo       Creating the virtual environment...
%PYEXE% -m venv ".venv"
if errorlevel 1 goto venv_fail
goto check_pkg

:have_venv
echo [1/3] Found the prepared environment.

:check_pkg
".venv\Scripts\python.exe" -c "import edge_tts, gtts, imageio_ffmpeg, PIL" >nul 2>nul
if not errorlevel 1 goto run_launcher

echo [2/3] Installing packages. First time takes 1-3 minutes.
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto pip_warn
goto run_launcher

:pip_warn
echo.
echo [NOTE] Package install did not finish. Check your internet connection.
echo        Coupas Hunter still works. TTS and Shorts will continue installing next run.
echo.

:run_launcher
echo [3/3] Checking for updates, starting the 4 servers, opening the app window.
echo.
if not exist ".venv\Scripts\pythonw.exe" goto run_console
start "" ".venv\Scripts\pythonw.exe" "%~dp0launcher.py"
timeout /t 2 >nul
echo    * No console window stays open. Servers run in the background.
echo    * Hub: http://127.0.0.1:8770/
echo    * Stop: stop.bat  /  Log: logs\launcher.log
echo    * Desktop shortcut: make-shortcut.bat
echo.
echo This window can be closed.
timeout /t 3 >nul
exit /b 0

:run_console
echo    (pythonw not found - running in this window)
".venv\Scripts\python.exe" launcher.py
goto end

:no_files
echo [ERROR] launcher.py not found. Please run this from the unzipped folder.
echo.
pause
goto end

:no_python
echo.
echo [ERROR] Python is not installed.
echo   1) Open https://www.python.org/downloads/windows/
echo   2) Install Python 3.12
echo   3) Check Add python.exe to PATH during setup
echo   4) Close this window and run this file again
echo.
pause
goto end

:old_python
echo.
echo [ERROR] Python 3.9 or newer is required.
echo.
pause
goto end

:venv_fail
echo.
echo [ERROR] Could not create .venv. Try unzipping to a simple path like C:\studio-launcher
echo.
pause
goto end

:end
echo.
echo Launcher stopped. You can close this window.
pause >nul
exit /b 0
