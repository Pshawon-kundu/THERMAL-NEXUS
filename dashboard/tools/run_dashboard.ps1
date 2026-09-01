param()

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$DashboardApp = Join-Path $RepoRoot "host\dashboard\app.py"

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python was not found: $PythonExe"
}

if (-not (Test-Path $DashboardApp)) {
    throw "Dashboard application was not found: $DashboardApp"
}

Set-Location $RepoRoot

# Allow Python and Streamlit to import the repository packages.
$env:PYTHONPATH = $RepoRoot

# Disable optional Streamlit usage-stat collection.
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"

Write-Host "Repository root: $RepoRoot"
Write-Host "Python: $PythonExe"
Write-Host "Dashboard: $DashboardApp"
Write-Host "Starting Thermal Nexus dashboard..."

& $PythonExe -m streamlit run $DashboardApp `
    --server.address localhost `
    --server.port 8501

exit $LASTEXITCODE