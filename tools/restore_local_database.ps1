param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$DatabasePath = "host/database/thermal_nexus.db",
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Database = Join-Path $RepoRoot $DatabasePath
$Backup = Resolve-Path $BackupPath

if (-not $ConfirmRestore) {
    throw "Restore is blocked. Re-run with -ConfirmRestore after verifying the backup path."
}

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python was not found: $PythonExe"
}

if (-not (Test-Path $Backup)) {
    throw "Backup not found: $Backup"
}

if (Test-Path $Database) {
    & (Join-Path $PSScriptRoot "backup_local_database.ps1") -DatabasePath $DatabasePath
}

Copy-Item -LiteralPath $Backup -Destination $Database -Force
& $PythonExe -m analysis.release_hardening validate
if ($LASTEXITCODE -ne 0) {
    throw "Restored database failed release validation."
}

Write-Host "Database restored from: $Backup"
