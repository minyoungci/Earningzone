@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo [오류] Python 3.10 이상을 설치하세요.
  pause
  exit /b 1
)
python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul
if errorlevel 1 (
  echo [오류] Python 3.10 이상이 필요합니다.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 exit /b 1
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1
python server\check_requirements.py >nul 2>nul
if errorlevel 1 (
  echo [setup] 필요한 패키지를 설치합니다...
  python -m pip install --disable-pip-version-check -r server\requirements.txt
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
python server\launch.py
if errorlevel 1 pause
endlocal
