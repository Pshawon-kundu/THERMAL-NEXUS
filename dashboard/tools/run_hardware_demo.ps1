# Run a Thermal Nexus hardware-phase campaign (simulated by default).
# Usage:
#   pwsh ./tools/run_hardware_demo.ps1                     # simulated
#   pwsh ./tools/run_hardware_demo.ps1 -Source measured     # measured (Phase 7)
#   pwsh ./tools/run_hardware_demo.ps1 -Output evidence/hardware/run_001

[CmdletBinding()]
param(
    [ValidateSet("simulated", "measured")]
    [string]$Source = "simulated",

    [string]$Config = "config/hardware_demo.yaml",

    [string]$Output = "",

    [string]$Database = "host/database/thermal_nexus.db",

    [string]$Operator = "simulator",

    [string]$FirmwareVersion = "0.0.0-simulated",

    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv/bin/python")) {
    throw "Virtual environment not found. Run tools/initialize_dashboard.ps1 first."
}

if ([string]::IsNullOrEmpty($Output)) {
    $Output = "evidence/hardware/run_$(Get-Date -Format 'yyyyMMddHHmmss')"
}

$VerboseFlag = if ($Verbose) { "--verbose" } else { "" }

Write-Host "[run_hardware_demo] source=$Source output=$Output db=$Database"
& .venv/bin/python -m simulator.hardware.run_hardware_demo `
    --source $Source `
    --config $Config `
    --output $Output `
    --database $Database `
    --operator $Operator `
    --firmware-version $FirmwareVersion `
    $VerboseFlag

if ($LASTEXITCODE -ne 0) {
    throw "run_hardware_demo exited with code $LASTEXITCODE"
}

Write-Host "[run_hardware_demo] Done. Artefacts in $Output"
