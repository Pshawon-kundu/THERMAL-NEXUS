param(
    [string]$DatabasePath = "host/database/thermal_nexus.db",
    [string]$OutputDir = "evidence/backups"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Database = Join-Path $RepoRoot $DatabasePath
$BackupRoot = Join-Path $RepoRoot $OutputDir

if (-not (Test-Path $Database)) {
    throw "Database not found: $Database"
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $BackupRoot "thermal_nexus_$Stamp.db"
Copy-Item -LiteralPath $Database -Destination $Backup
$Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $Backup
"$($Hash.Hash.ToLower())  $(Split-Path -Leaf $Backup)" | Set-Content -Encoding UTF8 "$Backup.sha256"

Write-Host "Backup created: $Backup"
Write-Host "Checksum: $($Hash.Hash.ToLower())"
