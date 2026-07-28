@echo off
REM AppForge AI - double-click launcher for Windows.
REM Delegates to start.ps1 with an execution policy that does not require
REM changing machine-wide PowerShell settings.

echo Starting AppForge AI...
echo.

where powershell >nul 2>nul
if errorlevel 1 (
    echo ERROR: PowerShell was not found on this system.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Seed %*

if errorlevel 1 (
    echo.
    echo Startup failed. See the messages above.
    pause
    exit /b 1
)

pause
