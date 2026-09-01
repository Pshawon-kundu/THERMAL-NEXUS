# KPI Reporting Guide

Generate KPI reports:

```powershell
.\tools\generate_kpi_reports.ps1
```

Reports are written under `evidence/kpi/<experiment_id>/` as CSV, JSON,
Markdown, and HTML. Compatible experiment comparisons are written under
`evidence/kpi/comparisons/`.

Single-run comparisons must not be interpreted as statistically significant.
