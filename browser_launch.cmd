@echo off
setlocal
chcp 65001 >nul
set "BROWSER_PYTHON="
if not exist "%~dp0config\browser_python.txt" (
  echo Run setup.ps1 first.
  exit /b 1
)
set /p "BROWSER_PYTHON="<"%~dp0config\browser_python.txt"
if not defined BROWSER_PYTHON (
  echo Configure the local Python path in config/browser_python.txt.
  exit /b 1
)
if not exist "%BROWSER_PYTHON%" (
  echo Configured Python was not found. Check config/browser_python.txt.
  exit /b 1
)
"%BROWSER_PYTHON%" -X utf8 "%~dp0browser_login.py" %* --config "%~dp0config\browser_login.toml"
exit /b %errorlevel%
