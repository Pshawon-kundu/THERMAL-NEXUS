# Software Release Guide

Thermal Nexus software RC1 is a reproducible software-only release candidate.
It packages the synthetic-data pipeline, provisional selected model, runtime
simulator, binary packet protocol, local reader, SQLite-backed dashboard, KPI
reports, and hardware-independent embedded preparation files.

All release evidence must include:

- `releases/software_rc1/RELEASE_MANIFEST.json`
- `releases/software_rc1/RELEASE_NOTES.md`
- `releases/software_rc1/CHECKSUMS.sha256`
- `releases/competition_software_evidence/INDEX.md`
- `releases/competition_software_evidence/LIMITATIONS.md`

Create and validate the release package:

```powershell
python -m analysis.release_hardening release
python -m analysis.release_hardening evidence
python -m analysis.release_hardening validate
```

The release manifest records the Git commit when available, selected model
version, model checksum, feature-schema checksum, protocol version, policy
version, database schema version, and frozen configuration checksums.

This release makes no physical sensor accuracy, RF range, or battery-life claim.

