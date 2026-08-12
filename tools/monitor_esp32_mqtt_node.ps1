Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

pio device monitor -d firmware\esp32_mqtt_node -e esp32dev -b 115200
