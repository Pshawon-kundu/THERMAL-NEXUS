# Offline Dashboard Guide

Initialize the database:

```powershell
.\tools\initialize_dashboard.ps1
```

Import current end-to-end evidence:

```powershell
.\tools\import_latest_experiments.ps1
```

Run the offline dashboard:

```powershell
.\tools\run_dashboard.ps1
```

The dashboard is Streamlit-based, uses local SQLite files, and requires no
internet service. It displays a visible simulated-data warning.
