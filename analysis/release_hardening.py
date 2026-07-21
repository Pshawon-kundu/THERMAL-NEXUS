"""Release-candidate evidence and validation utilities."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from host.ingestion.checksums import sha256_file

REPO_ROOT = Path(__file__).resolve().parents[1]
SIMULATED_NOTICE = "SIMULATED SOFTWARE DATA - NOT PHYSICAL HARDWARE RESULTS"
SOFTWARE_VERSION = "software_rc1"
POLICY_VERSION = "runtime_policy_rc1"
PROTOCOL_VERSION = 1
DATABASE_SCHEMA_VERSION = 1
DEFAULT_RELEASE_DIR = Path("releases/software_rc1")
DEFAULT_EVIDENCE_DIR = Path("releases/competition_software_evidence")
DEFAULT_FINAL_DEMO_DIR = Path("evidence/final_demo")
DEFAULT_DATABASE_PATH = Path("host/database/thermal_nexus.db")


def selected_model_manifest() -> dict[str, Any]:
    """Load the selected-model pointer."""

    selected_path = REPO_ROOT / "ml/models/selected/latest_selected.json"
    if not selected_path.exists():
        raise FileNotFoundError(f"Selected-model pointer not found: {selected_path}")
    data = json.loads(selected_path.read_text(encoding="utf-8"))
    artifact_dir = REPO_ROOT / data["artifact_dir"]
    required = [
        "pipeline.joblib",
        "preprocessing.joblib",
        "feature_schema.json",
        "class_mapping.json",
        "configuration.yaml",
        "metrics_validation.json",
        "MODEL_CARD.md",
        "checksums.json",
    ]
    missing = [name for name in required if not (artifact_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Selected-model artifact is incomplete: {', '.join(missing)}"
        )
    data["artifact_dir"] = str(Path(data["artifact_dir"]))
    data["checksums"] = json.loads(
        (artifact_dir / "checksums.json").read_text(encoding="utf-8")
    )
    return data


def release_config_files() -> list[Path]:
    """Return frozen release configuration files."""

    return sorted((REPO_ROOT / "config/release").glob("*.yaml"))


def critical_artifacts() -> list[Path]:
    """Return critical files included in release integrity checks."""

    selected = selected_model_manifest()
    model_dir = REPO_ROOT / selected["artifact_dir"]
    files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "config/runtime_policy.yaml",
        REPO_ROOT / "config/radio_simulation.yaml",
        REPO_ROOT / "protocol/specification/PROTOCOL_V1.md",
        REPO_ROOT / "host/database/schema.py",
        model_dir / "pipeline.joblib",
        model_dir / "feature_schema.json",
        model_dir / "class_mapping.json",
        model_dir / "MODEL_CARD.md",
    ]
    files.extend(release_config_files())
    return [path for path in files if path.exists()]


def build_manifest() -> dict[str, Any]:
    """Build the release-candidate manifest."""

    selected = selected_model_manifest()
    selected_dir = REPO_ROOT / selected["artifact_dir"]
    config_checksums = {
        str(path.relative_to(REPO_ROOT)): sha256_file(path)
        for path in release_config_files()
    }
    artifact_checksums = {
        str(path.relative_to(REPO_ROOT)): sha256_file(path)
        for path in critical_artifacts()
    }
    return {
        "software_version": SOFTWARE_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "selected_model": selected["selected_model"],
        "selected_model_version": selected_dir.name,
        "selected_model_checksum": artifact_checksums.get(
            str((selected_dir / "pipeline.joblib").relative_to(REPO_ROOT))
        ),
        "feature_schema_checksum": artifact_checksums.get(
            str((selected_dir / "feature_schema.json").relative_to(REPO_ROOT))
        ),
        "policy_version": POLICY_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "database_schema_version": DATABASE_SCHEMA_VERSION,
        "configuration_checksums": config_checksums,
        "critical_artifact_checksums": artifact_checksums,
        "critical_artifact_paths": sorted(artifact_checksums),
        "limitations_notice": SIMULATED_NOTICE,
        "hardware_claims": "none",
    }


def create_release_candidate(
    output_dir: Path = DEFAULT_RELEASE_DIR,
) -> dict[str, Any]:
    """Create release-candidate manifest, notes, and checksum file."""

    resolved = REPO_ROOT / output_dir
    resolved.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    manifest_path = resolved / "RELEASE_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    _write_checksum_file(resolved / "CHECKSUMS.sha256", critical_artifacts())
    (resolved / "RELEASE_NOTES.md").write_text(
        _release_notes(manifest), encoding="utf-8"
    )
    return manifest


def create_competition_evidence_package(
    output_dir: Path = DEFAULT_EVIDENCE_DIR,
) -> dict[str, Any]:
    """Create a reviewed index for competition software evidence."""

    resolved = REPO_ROOT / output_dir
    resolved.mkdir(parents=True, exist_ok=True)
    entries = [
        "docs/SYSTEM_ARCHITECTURE.md",
        "docs/SOFTWARE_ROADMAP.md",
        "docs/RUNTIME_INFERENCE_SPECIFICATION.md",
        "docs/END_TO_END_SIMULATION_GUIDE.md",
        "evidence/end_to_end/runtime_report.md",
        "evidence/end_to_end/mode_comparison.csv",
        "evidence/dashboard/import_report.md",
        "releases/software_rc1/RELEASE_MANIFEST.json",
    ]
    existing = [path for path in entries if (REPO_ROOT / path).exists()]
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "software_version": SOFTWARE_VERSION,
        "limitations_notice": SIMULATED_NOTICE,
        "entries": existing,
        "checksums": {
            path: sha256_file(REPO_ROOT / path)
            for path in existing
            if (REPO_ROOT / path).is_file()
        },
    }
    (resolved / "EVIDENCE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    (resolved / "INDEX.md").write_text(_evidence_index(manifest), encoding="utf-8")
    (resolved / "LIMITATIONS.md").write_text(_limitations(), encoding="utf-8")
    return manifest


def create_final_demo_summary(
    output_dir: Path = DEFAULT_FINAL_DEMO_DIR,
) -> dict[str, Any]:
    """Create final-demo manifest, summary, and checksums."""

    resolved = REPO_ROOT / output_dir
    resolved.mkdir(parents=True, exist_ok=True)
    tracked = [
        path
        for path in [
            REPO_ROOT / "evidence/end_to_end/runtime_report.md",
            REPO_ROOT / "evidence/end_to_end/runtime_metrics.json",
            REPO_ROOT / "evidence/end_to_end/mode_comparison.csv",
            REPO_ROOT / "evidence/dashboard/import_report.md",
            REPO_ROOT / "embedded/generated/deployment_manifest.json",
        ]
        if path.exists()
    ]
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "software_version": SOFTWARE_VERSION,
        "demo_scope": "software-only simulation and offline evidence review",
        "limitations_notice": SIMULATED_NOTICE,
        "artifacts": [str(path.relative_to(REPO_ROOT)) for path in tracked],
        "checksums": {
            str(path.relative_to(REPO_ROOT)): sha256_file(path) for path in tracked
        },
    }
    (resolved / "demo_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    (resolved / "DEMO_SUMMARY.md").write_text(_demo_summary(manifest), encoding="utf-8")
    _write_checksum_file(resolved / "demo_checksums.sha256", tracked)
    return manifest


def validate_database(
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> str:
    """Run SQLite integrity validation."""

    resolved = REPO_ROOT / database_path
    if not resolved.exists():
        raise FileNotFoundError(f"Database not found: {resolved}")
    with sqlite3.connect(resolved) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    status = str(result[0]) if result else "missing integrity result"
    if status.lower() != "ok":
        raise RuntimeError(f"Database integrity check failed: {status}")
    return status


def validate_release_artifacts(
    release_dir: Path = DEFAULT_RELEASE_DIR,
) -> dict[str, Any]:
    """Validate release manifest checksums and selected-model requirements."""

    selected_model_manifest()
    validate_database()
    resolved = REPO_ROOT / release_dir
    manifest_path = resolved / "RELEASE_MANIFEST.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Release manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for relative, expected in manifest["critical_artifact_checksums"].items():
        path = REPO_ROOT / relative
        if not path.exists() or sha256_file(path) != expected:
            mismatches.append(relative)
    if mismatches:
        raise RuntimeError(f"Release checksum mismatch: {', '.join(mismatches)}")
    return {
        "status": "ok",
        "checked_artifacts": len(manifest["critical_artifact_checksums"]),
    }


def _write_checksum_file(path: Path, files: list[Path]) -> None:
    lines = [
        f"{sha256_file(file_path)}  {file_path.relative_to(REPO_ROOT).as_posix()}"
        for file_path in sorted(files)
        if file_path.is_file()
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _release_notes(manifest: dict[str, Any]) -> str:
    return f"""# Thermal Nexus Software RC1

{SIMULATED_NOTICE}

Software version: `{manifest["software_version"]}`
Git commit: `{manifest["git_commit"]}`
Selected model: `{manifest["selected_model_version"]}`
Policy version: `{manifest["policy_version"]}`
Protocol version: `{manifest["protocol_version"]}`
Database schema version: `{manifest["database_schema_version"]}`

This release candidate packages the software-only simulator, offline dashboard,
model runtime wrapper, binary protocol simulator, local reader, and evidence
reports. It does not include physical STM32 firmware, TMP117 measurements, or
XBee range validation.
"""


def _evidence_index(manifest: dict[str, Any]) -> str:
    lines = [
        "# Thermal Nexus Competition Software Evidence",
        "",
        SIMULATED_NOTICE,
        "",
        "## Included Evidence",
    ]
    lines.extend(f"- `{entry}`" for entry in manifest["entries"])
    return "\n".join(lines) + "\n"


def _limitations() -> str:
    return f"""# Limitations

{SIMULATED_NOTICE}

- Temperature data is synthetic unless explicitly imported through the real-data
  ingestion contract.
- Energy values are estimated software values, not measured watt-hour results.
- No RF range, packet-delivery, sensor-accuracy, or battery-life claim is made
  for physical hardware in this release.
- Learned-model results are preliminary and must be retrained and revalidated
  with real TMP117 runs before competition hardware claims.
"""


def _demo_summary(manifest: dict[str, Any]) -> str:
    lines = [
        "# Thermal Nexus Final Software Demo Summary",
        "",
        SIMULATED_NOTICE,
        "",
        f"Created: `{manifest['created_at_utc']}`",
        "",
        "## Reviewed Artifacts",
    ]
    lines.extend(f"- `{artifact}`" for artifact in manifest["artifacts"])
    return "\n".join(lines) + "\n"


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["release", "evidence", "demo", "validate"],
        help="Release-hardening action to execute.",
    )
    args = parser.parse_args()
    if args.command == "release":
        result = create_release_candidate()
    elif args.command == "evidence":
        result = create_competition_evidence_package()
    elif args.command == "demo":
        result = create_final_demo_summary()
    else:
        result = validate_release_artifacts()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
