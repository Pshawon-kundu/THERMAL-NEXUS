@echo off
setlocal EnableExtensions
title HART - Stop Dashboard
cd /d "%~dp0"

set "ROOT=%~dp0"
set "DASH=%ROOT%dashboard"
set "RUNTIME=%ROOT%.runtime"
set "PIDDIR=%RUNTIME%\pids"
set "HELPER=%RUNTIME%\hart.ps1"

echo [HART] Stopping HART dashboard services...

if exist "%HELPER%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action stop-all -PythonPath "%DASH%\.venv\Scripts\python.exe" -DashboardPath "%DASH%" -PidDir "%PIDDIR%"
) else (
    echo [HART] ERROR - helper script missing: %HELPER%
)

echo [HART] Dashboard stopped.
ping -n 5 127.0.0.1 >nul 2>&1
exit /b 0