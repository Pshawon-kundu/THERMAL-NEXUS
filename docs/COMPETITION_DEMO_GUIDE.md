# Competition Demo Guide

Run the complete software demonstration:

```powershell
.\tools\run_complete_software_demo.ps1
```

The script creates or validates release evidence, runs the three operating
modes, imports evidence into the local database, generates KPI reports, prepares
embedded-readiness artifacts, and executes pytest, Ruff, and Black.

Demo evidence is written under:

- `evidence/end_to_end/`
- `evidence/dashboard/`
- `evidence/kpi/`
- `evidence/final_demo/`
- `releases/software_rc1/`
- `releases/competition_software_evidence/`

Every demo result is a simulated software result unless explicitly replaced by
real TMP117, STM32U585, XBee-PRO, and reader evidence.

