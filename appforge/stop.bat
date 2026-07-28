@echo off
REM AppForge AI - stop the platform.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1" %*
pause
