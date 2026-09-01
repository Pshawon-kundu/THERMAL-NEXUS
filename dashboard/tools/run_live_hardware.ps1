param(
    [string]$Port = "COM10",
    [int]$Baud = 115200
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python was not found: $PythonExe (run: python -m venv .venv ; pip install -r requirements.txt)"
}

Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"

Write-Host "==================================================================="
Write-Host "  THERMAL NEXUS - LIVE HARDWARE TESTING"
Write-Host "  1. Serial ingestion  : $Port @ $Baud baud (separate window)"
Write-Host "  2. Streamlit dashboard: http://localhost:8501"
Write-Host "==================================================================="
Write-Host ""
Write-Host "IMPORTANT: close the Arduino IDE serial monitor on $Port first -"
Write-Host "only ONE process may own the COM port."

# 1) Serial ingestion in its own window (dashboard must never own the port).
$IngestionArgs = "-NoExit", "-ExecutionPolicy", "Bypass", "-File",
    (Join-Path $PSScriptRoot "run_serial_ingestion.ps1"),
    "-Port", $Port, "-Baud", ([string]$Baud)
Start-Process powershell -ArgumentList $IngestionArgs
Write-Host "Serial ingestion started in a separate window."

Start-Sleep -Seconds 3

# 2) Streamlit dashboard in the foreground.
Write-Host "Starting dashboard on http://localhost:8501 ..."
& $PythonExe -m streamlit run (Join-Path $RepoRoot "host\dashboard\app.py") `
    --server.address localhost `
    --server.port 8501
exit $LASTEXITCODE
