Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

netstat -ano | findstr :1883
