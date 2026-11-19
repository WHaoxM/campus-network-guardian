@echo off
setlocal
chcp 65001 >nul
set "CAMPUS_PYTHON="
if not exist "%~dp0config\browser_python.txt" (
  echo Run setup.ps1 first.
  exit /b 1
)
set /p "CAMPUS_PYTHON="<"%~dp0config\browser_python.txt"
if not defined CAMPUS_PYTHON exit /b 1
if "%~1"=="" (
  "%CAMPUS_PYTHON%" -X utf8 "%~dp0campus_maintenance.py" status --config "%~dp0config\campus.toml"
) else (
  "%CAMPUS_PYTHON%" -X utf8 "%~dp0campus_maintenance.py" --config "%~dp0config\campus.toml" %*
)
exit /b %errorlevel%
