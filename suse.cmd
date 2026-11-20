@echo off
setlocal DisableDelayedExpansion
set "runner=%~dp0app\scripts\suse.ps1"
if not exist "%runner%" set "runner=%~dp0scripts\suse.ps1"
if not exist "%runner%" (
    echo SUSE: Extract the entire ZIP before running suse.cmd.
    if "%~1"=="" pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%runner%" %*
set "result=%ERRORLEVEL%"
if not "%result%"=="0" if "%~1"=="" pause
exit /b %result%
