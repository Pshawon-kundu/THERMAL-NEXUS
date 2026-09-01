@echo off
setlocal EnableExtensions
title HART - Dashboard Setup
cd /d "%~dp0"

set "ROOT=%~dp0"
set "DASH=%ROOT%dashboard"
set "VENVPY=%DASH%\.venv\Scripts\python.exe"

echo.
echo ============================================================
echo   THERMAL NEXUS / HART  -  dashboard setup
echo ============================================================
echo.

if exist "%VENVPY%" goto :already

echo [HART] Creating a fresh virtual environment in:
echo [HART]   %DASH%\.venv
if not exist "%DASH%\.venv" goto :dovenv
rmdir /s /q "%DASH%\.venv"
:dovenv
python -m venv "%DASH%\.venv"
if errorlevel 1 goto :venv_fail
echo [HART] Virtual environment created.

set "LOCK=%DASH%\requirements.lock.txt"
set "REQ=%DASH%\requirements.txt"

if exist "%LOCK%" goto :install_lock
if exist "%REQ%" goto :install_req
echo [HART] ERROR: no requirements.lock.txt or requirements.txt found.
pause
exit /b 1

:install_lock
echo [HART] Installing pinned dependencies from requirements.lock.txt...
"%VENVPY%" -m pip install --disable-pip-version-check -r "%LOCK%"
if errorlevel 1 goto :install_fail
goto :verify

:install_req
echo [HART] Installing dependencies from requirements.txt...
"%VENVPY%" -m pip install --disable-pip-version-check -r "%REQ%"
if errorlevel 1 goto :install_fail
goto :verify

:verify
echo [HART] Verifying imports...
"%VENVPY%" -c "import streamlit, pyserial, pandas, numpy, yaml; print('dependencies OK')"
if errorlevel 1 goto :verify_fail
echo.
echo [HART] Setup complete.
echo [HART] Double-click run_dashboard.bat to start the dashboard.
echo.
pause
exit /b 0

:already
echo [HART] Virtual environment already present:
echo [HART]   %VENVPY%
echo [HART] Nothing to do. Double-click run_dashboard.bat to start.
echo.
pause
exit /b 0

:install_fail
echo [HART] ERROR: dependency installation failed.
pause
exit /b 1

:verify_fail
echo [HART] ERROR: import verification failed.
pause
exit /b 1

:venv_fail
echo [HART] ERROR: failed to create the virtual environment.
echo [HART] Install Python 3.10 or newer and try again.
pause
exit /b 1