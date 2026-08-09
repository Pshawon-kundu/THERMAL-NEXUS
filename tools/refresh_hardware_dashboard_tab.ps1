# Refresh the dashboard after a new hardware run:
#   1. Re-run migrations (idempotent).
#   2. Re-generate KPI reports.
#   3. Touch the Streamlit cache so the Hardware tab re-queries SQLite.
#
# This does NOT restart the dashboard process. The user must reload the
# browser tab or let Streamlit's auto-rerun pick up the new data.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "[refresh_hardware_dashboard_tab] Running migrations..."
& .venv/bin/python -m host.database.migrations

Write-Host "[refresh_hardware_dashboard_tab] Regenerating KPI reports..."
& .venv/bin/python -m analysis.kpi_reports --database host/database/thermal_nexus.db --output evidence/kpi

# Touch the Streamlit cache + log so the dashboard re-fetches on next interaction.
$logFile = "host/dashboard/streamlit.log"
if (Test-Path $logFile) {
    (Get-Item $logFile).LastWriteTime = Get-Date
}

Write-Host "[refresh_hardware_dashboard_tab] Done. Reload the Hardware tab in your browser."
