@echo off
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"
title 통합 스튜디오 런처 - TTS · 쇼츠 · 쿠파스
color 0B

echo ==========================================================
echo    통합 스튜디오 런처  -  TTS · 쇼츠 · 쿠파스
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
echo [1/3] 처음 한 번만 준비합니다. 1~3분 걸려요.
echo       가상환경을 만드는 중...
%PYEXE% -m venv ".venv"
if errorlevel 1 goto venv_fail
goto check_pkg

:have_venv
echo [1/3] 준비된 환경을 찾았습니다.

:check_pkg
".venv\Scripts\python.exe" -c "import edge_tts, imageio_ffmpeg, PIL" >nul 2>nul
if not errorlevel 1 goto run_launcher

echo [2/3] 필요한 패키지를 설치하는 중... 처음엔 1~3분 걸려요.
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto pip_warn
goto run_launcher

:pip_warn
echo.
echo [알림] 패키지 설치가 끝나지 않았습니다. 인터넷 연결을 확인해 주세요.
echo        쿠파스 헌터는 그대로 쓸 수 있고요, TTS·쇼츠는 다음 실행 때 이어서 설치합니다.
echo.

:run_launcher
echo [3/3] 서버 3개를 켜고 브라우저를 엽니다.
echo.
echo    * 이 검은 창을 닫으면 서버도 같이 꺼집니다.
echo    * 허브 주소: http://127.0.0.1:8770
echo.
".venv\Scripts\python.exe" launcher.py
goto end

:no_files
echo [문제] launcher.py 를 찾을 수 없습니다.
echo        ZIP 압축을 푼 폴더 안에서 실행해 주세요.
echo.
pause
goto end

:no_python
echo.
echo [문제] Python 이 설치되어 있지 않습니다.
echo.
echo   1) https://www.python.org/downloads/windows/ 접속
echo   2) Download Python 3.12 설치
echo   3) 설치 첫 화면에서 Add python.exe to PATH 를 꼭 체크
echo   4) 이 창을 닫고 실행하기.bat 을 다시 더블클릭
echo.
pause
goto end

:old_python
echo.
echo [문제] Python 버전이 너무 낮습니다. 3.9 이상이 필요합니다.
echo        https://www.python.org/downloads/windows/ 에서 새로 설치해 주세요.
echo.
pause
goto end

:venv_fail
echo.
echo [문제] 가상환경을 만들지 못했습니다.
echo        폴더 경로에 특수문자가 있거나 권한 문제일 수 있습니다.
echo        C:\studio-launcher 처럼 단순한 경로에 다시 풀어 보세요.
echo.
pause
goto end

:end
echo.
echo 런처가 끝났습니다. 이 창은 닫아도 됩니다.
pause >nul
exit /b 0
