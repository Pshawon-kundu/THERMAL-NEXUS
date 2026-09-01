# Embedded Deployment Specification

Prepare embedded export files:

```powershell
.\tools\prepare_embedded_export.ps1
```

Generated files are hardware-independent C99 preparation artifacts under
`embedded/generated/`. They do not include STM32 HAL calls, TMP117 drivers, or
XBee drivers.

Supported selected model exporters:

- `DecisionTreeClassifier`
- `LogisticRegression`
- `MLPClassifier`

Random Forest remains a reference model and is rejected unless a future exporter
is explicitly approved.
