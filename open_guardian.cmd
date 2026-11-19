@echo off
setlocal
if not exist "%~dp0runtime\desktop\CampusGuardian.exe" (
  echo CampusGuardian.exe is missing. Extract the full Windows package.
  pause
  exit /b 1
)
start "" "%~dp0runtime\desktop\CampusGuardian.exe"
