param(
    [string]$Input = "evidence\end_to_end\ml\node_decisions.csv",
    [double]$Speed = 10.0,
    [switch]$Realtime
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python was not found: $PythonExe"
}

Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot

$argsList = @("-m", "host.mqtt.simulator", "--input", $Input, "--speed", "$Speed")
if ($Realtime) {
    $argsList += "--realtime"
}

Write-Host "Publishing simulated Thermal Nexus MQTT messages..."
& $PythonExe @argsList
exit $LASTEXITCODE

