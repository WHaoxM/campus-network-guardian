@echo off
call "%~dp0campus_maintenance.cmd" logs --follow %*
exit /b %errorlevel%
