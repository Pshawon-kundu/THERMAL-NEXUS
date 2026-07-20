# Experiment Ingestion Guide

Import one mode directory:

```powershell
python -m host.ingestion.import_experiment `
  --input evidence/end_to_end/fixed `
  --database host/database/thermal_nexus.db
```

Import all complete mode directories recursively:

```powershell
python -m host.ingestion.import_experiment `
  --input evidence/end_to_end `
  --recursive `
  --database host/database/thermal_nexus.db
```

The importer validates required files and columns, computes SHA-256 checksums,
uses a transaction, and skips duplicate imports.
