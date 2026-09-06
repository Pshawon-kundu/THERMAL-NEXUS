# HART dashboard runtime helper - used ONLY by run_dashboard.bat /
# stop_dashboard.bat. Keeps PID tracking and process checks in one place.
#
# Actions:
#   check-serial     exit 0 if ANY python process runs host.ingestion.serial_service
#                    (any location - a duplicate COM owner must never be started).
#   check-streamlit  exit 0 if a streamlit process is already listening on :8501.
#   start-serial     launch serial_service from the given dashboard venv, write pid.
#   start-streamlit  launch streamlit on localhost:8501, write pid.
#   start-api        launch the read-only telemetry API on localhost:8502, write pid.
#   stop-all         stop ONLY python processes from THIS dashboard venv that run
#                    streamlit, serial_service or the telemetry API; clean pid files.

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("check-serial", "check-streamlit", "port-busy", "start-serial", "start-streamlit", "start-api", "stop-all")]
    [string]$Action,
    [string]$PythonPath = "",
    [string]$DashboardPath = "",
    [string]$PidDir = "",
    [string]$SerialPort = ""
)

$ErrorActionPreference = "SilentlyContinue"

function Get-HartOwnedProcs {
    $venvPython = Join-Path $DashboardPath ".venv\Scripts\python.exe"
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            ($_.ExecutablePath -ieq $venvPython) -and
            ($_.CommandLine -match "streamlit" -or $_.CommandLine -match "serial_service" -or $_.CommandLine -match "host.api.server")
        }
}

switch ($Action) {
    "check-serial" {
        $any = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object { $_.CommandLine -match "host\.ingestion\.serial_service" }
        if ($any) { exit 0 } else { exit 1 }
    }
    "check-streamlit" {
        $listeners = Get-NetTCPConnection -LocalPort 8501 -State Listen
        foreach ($conn in $listeners) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)"
            if ($proc -and ($proc.CommandLine -match "streamlit")) { exit 0 }
        }
        exit 1
    }
    "port-busy" {
        # exit 0 if ANY listener occupies 8501 (used to detect a conflicting program).
        $listeners = @(Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) { exit 0 } else { exit 1 }
    }
    "start-serial" {
        $argsList = @('-m', 'host.ingestion.serial_service')
        if ($SerialPort) { $argsList += @('--port', $SerialPort) }
        $logDir = Join-Path (Split-Path $PidDir -Parent) 'logs'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $p = Start-Process -FilePath $PythonPath -ArgumentList $argsList `
            -WorkingDirectory $DashboardPath -WindowStyle Minimized -PassThru `
            -RedirectStandardOutput (Join-Path $logDir 'serial.log') `
            -RedirectStandardError (Join-Path $logDir 'serial.err.log')
        if ($p) {
            New-Item -ItemType Directory -Force -Path $PidDir | Out-Null
            Set-Content -Path (Join-Path $PidDir "serial.pid") -Value $p.Id -Encoding ascii
            Write-Host "[HART] serial_service started (pid=$($p.Id))"
            exit 0
        }
        exit 1
    }
    "start-streamlit" {
        $env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
        $argsList = @(
            '-m', 'streamlit', 'run', 'host\dashboard\app.py',
            '--server.address', 'localhost', '--server.port', '8501',
            '--server.headless', 'true'
        )
        $logDir = Join-Path (Split-Path $PidDir -Parent) 'logs'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $p = Start-Process -FilePath $PythonPath -ArgumentList $argsList `
            -WorkingDirectory $DashboardPath -WindowStyle Minimized -PassThru `
            -RedirectStandardOutput (Join-Path $logDir 'streamlit.log') `
            -RedirectStandardError (Join-Path $logDir 'streamlit.err.log')
        if ($p) {
            New-Item -ItemType Directory -Force -Path $PidDir | Out-Null
            Set-Content -Path (Join-Path $PidDir "streamlit.pid") -Value $p.Id -Encoding ascii
            Write-Host "[HART] streamlit started (pid=$($p.Id))"
            exit 0
        }
        exit 1
    }
    "start-api" {
        $argsList = @('-m', 'host.api.server', '--port', '8502')
        $logDir = Join-Path (Split-Path $PidDir -Parent) 'logs'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $p = Start-Process -FilePath $PythonPath -ArgumentList $argsList `
            -WorkingDirectory $DashboardPath -WindowStyle Minimized -PassThru `
            -RedirectStandardOutput (Join-Path $logDir 'api.log') `
            -RedirectStandardError (Join-Path $logDir 'api.err.log')
        if ($p) {
            New-Item -ItemType Directory -Force -Path $PidDir | Out-Null
            Set-Content -Path (Join-Path $PidDir "api.pid") -Value $p.Id -Encoding ascii
            Write-Host "[HART] telemetry API started (pid=$($p.Id))"
            exit 0
        }
        exit 1
    }
    "stop-all" {
        $procs = @(Get-HartOwnedProcs)
        foreach ($proc in $procs) {
            Write-Host "[HART] Stopping PID $($proc.ProcessId): $($proc.CommandLine)"
            # Use the full process TREE (/T): the venv python.exe may be a small
            # launcher whose real worker (base interpreter) is its child process
            # on this machine, and the child owns the COM port / port 8501.
            & taskkill /PID $proc.ProcessId /T /F 2>$null | Out-Null
        }
        # Also release any processes whose parent already died but which were
        # started from this venv (orphaned children) - match by command line only.
        $orphans = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object {
                $_.CommandLine -match "host\.ingestion\.serial_service|streamlit run|host\.api\.server" -and
                $_.ExecutablePath -imatch "PythonSoftwareFoundation"
            }
        foreach ($orc in $orphans) {
            & taskkill /PID $orc.ProcessId /T /F 2>$null | Out-Null
        }
        Remove-Item (Join-Path $PidDir "serial.pid") -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $PidDir "streamlit.pid") -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $PidDir "api.pid") -ErrorAction SilentlyContinue
        if ($procs.Count -gt 0) {
            Write-Host "[HART] Stopped $($procs.Count) HART service process tree(s)."
        } else {
            Write-Host "[HART] No HART dashboard services were running."
        }
        exit 0
    }
}