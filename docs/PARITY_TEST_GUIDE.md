# Parity Test Guide

Run:

```powershell
.\tools\run_embedded_parity.ps1
```

If a C compiler is available, the portable C harness is compiled and run against
golden vectors. If no compiler is available, the parity report is marked
`blocked_no_compiler` with instructions instead of claiming success.

Outputs:

- `evidence/embedded/parity_report.json`
- `evidence/embedded/PARITY_REPORT.md`
