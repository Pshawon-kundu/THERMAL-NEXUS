"""Audit synthetic Thermal Nexus datasets and write manifest evidence."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from simulator.temperature.generator import REQUIRED_COLUMNS

LOGGER = logging.getLogger(__name__)
DEFAULT_MANIFEST = Path("ml/data/processed/dataset_manifest.csv")
DEFAULT_REPORT_JSON = Path("evidence/dataset_audit_report.json")
DEFAULT_REPORT_MD = Path("evidence/dataset_audit_report.md")


class DatasetAuditError(ValueError):
    """Raised when a dataset audit fails."""


@dataclass(frozen=True)
class AuditResult:
    """Dataset audit result."""

    manifest: pd.DataFrame
    report: dict[str, Any]


def audit_dataset(
    input_dir: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    report_json_path: Path = DEFAULT_REPORT_JSON,
    report_md_path: Path = DEFAULT_REPORT_MD,
    scenarios_config_path: Path = Path("config/scenarios.yaml"),
) -> AuditResult:
    """Audit all synthetic CSV files in a directory."""

    csv_paths = sorted(input_dir.glob("*.csv"))
    if not csv_paths:
        raise DatasetAuditError(f"No CSV files found under {input_dir}.")

    scenarios = _recognized_scenarios(scenarios_config_path)
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    seen_run_ids: set[str] = set()

    for csv_path in csv_paths:
        row, row_issues, run_id = _audit_one_csv(csv_path, scenarios)
        if run_id in seen_run_ids:
            row_issues.append(f"Duplicate run_id found across CSV files: {run_id}")
        if run_id:
            seen_run_ids.add(run_id)
        row["status"] = "pass" if not row_issues else "fail"
        row["issues"] = "; ".join(row_issues)
        rows.append(row)
        issues.extend(f"{csv_path.name}: {issue}" for issue in row_issues)

    manifest = pd.DataFrame(rows).sort_values(["scenario", "run_id", "csv_path"])
    report = {
        "status": "pass" if not issues else "fail",
        "input_dir": str(input_dir),
        "runs_audited": int(len(manifest)),
        "recognized_scenarios": sorted(scenarios),
        "issues": issues,
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(manifest_path, index=False)
    report_json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report_md_path.write_text(_audit_markdown(report, manifest), encoding="utf-8")

    if issues:
        raise DatasetAuditError(f"Dataset audit failed with {len(issues)} issue(s).")
    return AuditResult(manifest=manifest, report=report)


def _audit_one_csv(
    csv_path: Path, scenarios: set[str]
) -> tuple[dict[str, Any], list[str], str | None]:
    issues: list[str] = []
    metadata_path = csv_path.with_suffix(".metadata.json")
    metadata: dict[str, Any] = {}
    frame = pd.DataFrame()
    run_id: str | None = None

    try:
        frame = pd.read_csv(csv_path)
    except Exception as exc:
        issues.append(f"CSV is not readable: {exc}")

    if not metadata_path.exists():
        issues.append("Matching metadata JSON is missing.")
    else:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append(f"Metadata JSON is not readable: {exc}")

    if not frame.empty:
        issues.extend(_validate_frame(frame, scenarios))
        run_ids = frame["run_id"].dropna().astype(str).unique()
        run_id = run_ids[0] if len(run_ids) == 1 else None
        if len(run_ids) != 1:
            issues.append("CSV must contain exactly one run_id.")
        if metadata:
            issues.extend(_validate_metadata(frame, metadata, run_id))

    row = {
        "run_id": run_id or metadata.get("run_id", ""),
        "scenario": _single_value(frame, "scenario") if not frame.empty else "",
        "csv_path": str(csv_path),
        "metadata_path": str(metadata_path),
        "sample_count": int(len(frame)),
        "valid_sample_count": (
            int(_bool_series(frame["sensor_valid"]).sum())
            if "sensor_valid" in frame
            else 0
        ),
        "random_seed": _single_value(frame, "random_seed") if not frame.empty else "",
    }
    return row, issues, run_id


def _validate_frame(frame: pd.DataFrame, scenarios: set[str]) -> list[str]:
    issues: list[str] = []
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in frame.columns]
    if missing_columns:
        return [f"Missing required columns: {', '.join(missing_columns)}"]

    if frame["scenario"].nunique(dropna=False) != 1:
        issues.append("CSV must contain exactly one scenario.")
    elif str(frame["scenario"].iloc[0]) not in scenarios:
        issues.append(f"Unrecognized scenario: {frame['scenario'].iloc[0]}")

    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    if timestamps.isna().any():
        issues.append("timestamp contains unreadable values.")
    else:
        seconds = (timestamps - timestamps.iloc[0]).dt.total_seconds()
        if (seconds < 0).any():
            issues.append("timestamps produce negative elapsed time.")
        if not timestamps.is_monotonic_increasing:
            issues.append("timestamps must be ordered.")

    lower = pd.to_numeric(frame["lower_limit"], errors="coerce")
    upper = pd.to_numeric(frame["upper_limit"], errors="coerce")
    if lower.isna().any() or upper.isna().any() or not (lower < upper).all():
        issues.append("lower_limit must be less than upper_limit for every row.")

    true_temperature = pd.to_numeric(frame["true_temperature"], errors="coerce")
    if true_temperature.isna().any():
        issues.append("true_temperature must be numeric for every row.")

    sensor_valid = _bool_series(frame["sensor_valid"])
    measured = pd.to_numeric(frame["measured_temperature"], errors="coerce")
    if measured[sensor_valid].isna().any():
        issues.append("measured_temperature must be numeric when sensor_valid is true.")
    if measured[~sensor_valid].notna().any():
        issues.append("invalid samples must have blank measured_temperature.")
    if frame["sensor_valid"].isna().any():
        issues.append("invalid samples must be explicitly marked in sensor_valid.")

    return issues


def _validate_metadata(
    frame: pd.DataFrame, metadata: dict[str, Any], run_id: str | None
) -> list[str]:
    issues: list[str] = []
    if metadata.get("run_id") != run_id:
        issues.append("Metadata run_id does not match CSV.")
    if metadata.get("scenario") != _single_value(frame, "scenario"):
        issues.append("Metadata scenario does not match CSV.")
    if int(metadata.get("sample_count", -1)) != len(frame):
        issues.append("Metadata sample_count does not match CSV.")
    valid_count = int(_bool_series(frame["sensor_valid"]).sum())
    if int(metadata.get("valid_sample_count", -1)) != valid_count:
        issues.append("Metadata valid_sample_count does not match CSV.")
    if int(metadata.get("random_seed", -1)) != int(_single_value(frame, "random_seed")):
        issues.append("Metadata random_seed does not match CSV.")
    return issues


def _recognized_scenarios(path: Path) -> set[str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return set(raw["scenarios"].keys())


def _single_value(frame: pd.DataFrame, column: str) -> object:
    values = frame[column].dropna().unique()
    return values[0] if len(values) else ""


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _audit_markdown(report: dict[str, Any], manifest: pd.DataFrame) -> str:
    scenario_counts = manifest.groupby("scenario").size().to_dict()
    lines = [
        "# Dataset Audit Report",
        "",
        f"Status: `{report['status']}`",
        f"Runs audited: {report['runs_audited']}",
        "",
        "## Scenario Counts",
        "",
    ]
    lines.extend(
        f"- {name}: {count}" for name, count in sorted(scenario_counts.items())
    )
    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        lines.extend(f"- {issue}" for issue in report["issues"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run dataset audit from the command line."""

    parser = argparse.ArgumentParser(description="Audit Thermal Nexus synthetic data.")
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        result = audit_dataset(args.input)
    except DatasetAuditError as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Audit passed for %s run(s).", result.report["runs_audited"])
    LOGGER.info("Manifest: %s", DEFAULT_MANIFEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
