Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

pio run -d firmware\esp32_mqtt_node -e esp32dev -t upload
