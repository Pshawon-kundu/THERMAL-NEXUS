# Verify the Phase-2 hardware targets were met by the latest hardware run.
# Reads the latest HARDWARE_KPI_BLOCK emitted by run_hardware_demo and
# checks each Phase-2 acceptance threshold.

[CmdletBinding()]
param(
    [string]$Database = "host/database/thermal_nexus.db"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Run the demo in dry-print mode by reading directly from SQLite.
$query = @"
SELECT
    hr.run_id,
    hr.source,
    (SELECT MAX(mt.distance_m) FROM measurement_traces mt
        WHERE mt.run_id = hr.run_id AND mt.per < 0.5) AS range_m,
    (SELECT MAX(ABS(pm.error_c)) FROM physical_measurements pm
        WHERE pm.run_id = hr.run_id) AS accuracy_max_error,
    (SELECT SUM(bi.total_cost_usd) FROM bom_items bi
        WHERE bi.run_id = hr.run_id) AS bom_cost,
    (SELECT SUM(bi.weight_g * bi.quantity) FROM bom_items bi
        WHERE bi.run_id = hr.run_id) AS weight_g,
    (SELECT SUM(bi.volume_cm3 * bi.quantity) FROM bom_items bi
        WHERE bi.run_id = hr.run_id) AS volume_cm3
FROM hardware_runs hr
ORDER BY hr.started_at DESC
LIMIT 1;
"@

$result = & .venv/bin/python -c @"
import sqlite3
con = sqlite3.connect('$Database')
con.row_factory = sqlite3.Row
row = con.execute('''$query''').fetchone()
if row is None:
    raise SystemExit('NO_HARDWARE_RUNS')
print('run_id              :', row['run_id'])
print('source              :', row['source'])
print('range_m_lt_50pct    :', row['range_m'])
print('accuracy_max_error  :', row['accuracy_max_error'])
print('bom_cost_usd        :', row['bom_cost'])
print('weight_g            :', row['weight_g'])
print('volume_cm3          :', row['volume_cm3'])
"@

if ($LASTEXITCODE -ne 0) {
    Write-Error "SQLite verification failed: $result"
    exit 1
}

Write-Host $result

# Soft thresholds for Phase 2 IEEE HART challenge
$min_range = 60.0
$max_error = 0.5
$max_cost = 75.0
$max_weight = 80.0
$max_volume = 250.0

$range_ok = [double]($result | Select-String "range_m_lt_50pct" | ForEach-Object { ($_ -split ':')[1].Trim() }) -ge $min_range
$error_ok = [double]($result | Select-String "accuracy_max_error" | ForEach-Object { ($_ -split ':')[1].Trim() }) -le $max_error
$cost_ok = [double]($result | Select-String "bom_cost_usd" | ForEach-Object { ($_ -split ':')[1].Trim() }) -le $max_cost
$weight_ok = [double]($result | Select-String "weight_g" | ForEach-Object { ($_ -split ':')[1].Trim() }) -le $max_weight
$volume_ok = [double]($result | Select-String "volume_cm3" | ForEach-Object { ($_ -split ':')[1].Trim() }) -le $max_volume

$summary = [pscustomobject]@{
    range_ok = $range_ok
    error_ok = $error_ok
    cost_ok = $cost_ok
    weight_ok = $weight_ok
    volume_ok = $volume_ok
}

if ($range_ok -and $error_ok -and $cost_ok -and $weight_ok -and $volume_ok) {
    Write-Host "[verify_hardware_phase] ✅ All Phase-2 KPI targets met."
    exit 0
}
Write-Host "[verify_hardware_phase] ⚠️  KPI thresholds:" $summary
exit 1
