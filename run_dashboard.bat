@echo off
setlocal EnableExtensions
title HART - Thermal Nexus Dashboard
cd /d "%~dp0"

set "ROOT=%~dp0"
set "DASH=%ROOT%dashboard"
set "VENVPY=%DASH%\.venv\Scripts\python.exe"
set "RUNTIME=%ROOT%.runtime"
set "PIDDIR=%RUNTIME%\pids"
set "HELPER=%RUNTIME%\hart.ps1"

echo.
echo ============================================================
echo   THERMAL NEXUS / HART  -  one-click dashboard launcher
echo ============================================================
echo.

if exist "%VENVPY%" goto :venv_ok
echo [HART] ERROR: virtual environment not found.
echo [HART] Expected: %VENVPY%
echo [HART] Double-click setup_dashboard.bat once to create it,
echo [HART] then re-run this file.
echo.
pause
exit /b 1
:venv_ok

if exist "%HELPER%" goto :helper_ok
echo [HART] ERROR: runtime helper not found: %HELPER%
pause
exit /b 1
:helper_ok

echo [HART] Dashboard : %DASH%
echo [HART] Python     : %VENVPY%
echo.

rem ---------- 1. serial ingestion - only ONE long-lived COM owner ----------
powershell -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action check-serial
if errorlevel 1 goto :start_serial
echo [HART] Serial ingestion already running - second instance NOT started.
goto :serial_ready
:start_serial
echo [HART] Starting serial ingestion...
powershell -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action start-serial -PythonPath "%VENVPY%" -DashboardPath "%DASH%" -PidDir "%PIDDIR%"
if errorlevel 1 goto :serial_fail
echo [HART] Serial ingestion running.
goto :serial_ready
:serial_fail
echo [HART] ERROR: could not launch serial ingestion.
echo [HART]        See %RUNTIME%\logs\serial.err.log
:serial_ready

rem ---------- 2. streamlit - single instance on localhost:8501 ----------
powershell -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action check-streamlit
if errorlevel 1 goto :check_port
echo [HART] Streamlit already running on localhost:8501 - reusing it.
goto :open_browser
:check_port
powershell -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action port-busy
if errorlevel 1 goto :start_streamlit
echo [HART] WARNING: port 8501 is used by a different program - Streamlit NOT started.
goto :open_browser
:start_streamlit
echo [HART] Starting dashboard...
powershell -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action start-streamlit -PythonPath "%VENVPY%" -DashboardPath "%DASH%" -PidDir "%PIDDIR%"
if errorlevel 1 goto :streamlit_fail
echo [HART] Streamlit started.
goto :open_browser
:streamlit_fail
echo [HART] ERROR: could not launch Streamlit.
echo [HART]        See %RUNTIME%\logs\streamlit.err.log
:open_browser

rem ---------- 3. open the browser ----------
echo.
echo [HART] Opening the dashboard in your default browser...
start "" "http://localhost:8501"
timeout /t 4 /nobreak >nul 2>&1

echo.
echo [HART] Dashboard is running. Keep this window open.
echo [HART] To stop the dashboard and ingestion cleanly,
echo [HART] double-click stop_dashboard.bat. Only HART processes are stopped.
echo.

rem ---------- 4. wait while the dashboard runs ----------
set "ST_UP=0"
set /a ST_WAITS=0
:WAIT
timeout /t 5 /nobreak >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Action check-streamlit
if errorlevel 1 goto :WAIT_DOWN
set "ST_UP=1"
set /a ST_WAITS=0
goto :WAIT

:WAIT_DOWN
if "%ST_UP%"=="1" goto :DONE
set /a ST_WAITS+=1
if %ST_WAITS% GEQ 24 goto :ST_NEVER
goto :WAIT

:ST_NEVER
echo [HART] Streamlit did not come up on port 8501.
echo [HART] Check %RUNTIME%\logs\streamlit.err.log
goto :DONE

:DONE
echo.
echo [HART] Streamlit stopped - closing launcher.
timeout /t 3 /nobreak >nul 2>&1
exit /b 0