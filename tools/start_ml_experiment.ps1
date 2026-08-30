param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [string]$Scenario,

    [Parameter(Mandatory = $true)]
    [string]$Node,

    [switch]$PhysicalSensor,

    [string]$Database = "host/database/thermal_nexus.db",
    [string]$CargoProfileId = "",
    [string]$ContainerProfileId = "",
    [string]$PayloadClass = "",
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$ArgsList = @(
    "-m", "ml.cargo_aware_v2.experiment_collector", "start",
    "--run-id", $RunId,
    "--scenario", $Scenario,
    "--node", $Node,
    "--database", $Database
)
if ($PhysicalSensor) { $ArgsList += "--physical-sensor" }
if ($CargoProfileId -ne "") { $ArgsList += @("--cargo-profile-id", $CargoProfileId) }
if ($ContainerProfileId -ne "") {
    $ArgsList += @("--container-profile-id", $ContainerProfileId)
}
if ($PayloadClass -ne "") { $ArgsList += @("--payload-class", $PayloadClass) }
if ($Notes -ne "") { $ArgsList += @("--notes", $Notes) }

& $Python @ArgsList
if ($LASTEXITCODE -ne 0) {
    throw "Failed to start ML experiment."
}
