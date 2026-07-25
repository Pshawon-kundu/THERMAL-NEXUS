param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
& $Python -m ml.external_t15.cli audit

