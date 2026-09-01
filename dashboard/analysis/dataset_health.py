"""Dataset health audit for model-ready Thermal Nexus splits."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.features.feature_schema import model_feature_columns

LOGGER = logging.getLogger(__name__)
OUT_DIR = Path("evidence/eda")


class DatasetHealthError(ValueError):
    """Raised when split health checks fail."""


def analyze_dataset_health(
    train_path: Path,
    validation_path: Path,
    test_path: Path,
    output_dir: Path = OUT_DIR,
) -> dict[str, Any]:
    """Analyze split health and write reports."""

    splits = {
        "train": pd.read_csv(train_path),
        "validation": pd.read_csv(validation_path),
        "test": pd.read_csv(test_path),
    }
    combined = pd.concat(splits, names=["split"]).reset_index(level=0)
    feature_columns = model_feature_columns(combined)
    numeric_features = [
        col for col in feature_columns if pd.api.types.is_numeric_dtype(combined[col])
    ]
    issues = _fail_fast_issues(splits, feature_columns)
    report = {
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "total_rows": int(len(combined)),
        "total_runs": int(combined["run_id"].nunique()),
        "runs_by_scenario": _count_dict(combined.drop_duplicates("run_id")["scenario"]),
        "rows_by_thermal_state": _count_dict(combined["thermal_state"]),
        "invalid_and_unavailable_rows": {
            "feature_invalid": int((~combined["feature_valid"].astype(bool)).sum()),
            "unavailable_targets": int(combined["thermal_state"].isna().sum()),
        },
        "missing_value_counts": {
            col: int(value)
            for col, value in combined.isna().sum().items()
            if int(value) > 0
        },
        "feature_validity_counts": _count_dict(combined["feature_valid"]),
        "duplicate_rows": int(combined.drop(columns=["split"]).duplicated().sum()),
        "duplicate_timestamps_within_run": _duplicate_timestamps(combined),
        "constant_or_near_constant_features": _near_constant(
            combined, numeric_features
        ),
        "highly_correlated_features": _highly_correlated(combined, numeric_features),
        "features_with_infinite_values": _infinite_features(combined, numeric_features),
        "features_with_nan_values": _nan_features(combined, feature_columns),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _feature_summary(combined, numeric_features).to_csv(
        output_dir / "feature_summary.csv", index=False
    )
    _class_by_split(splits).to_csv(
        output_dir / "class_distribution_by_split.csv", index=False
    )
    _class_by_scenario(combined).to_csv(
        output_dir / "class_distribution_by_scenario.csv", index=False
    )
    (output_dir / "dataset_health_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (output_dir / "dataset_health_report.md").write_text(
        _health_markdown(report), encoding="utf-8"
    )
    if issues:
        raise DatasetHealthError("; ".join(issues))
    return report


def _fail_fast_issues(
    splits: dict[str, pd.DataFrame], feature_columns: list[str]
) -> list[str]:
    issues: list[str] = []
    run_sets = {name: set(frame["run_id"].unique()) for name, frame in splits.items()}
    overlaps = {
        "train_validation": run_sets["train"] & run_sets["validation"],
        "train_test": run_sets["train"] & run_sets["test"],
        "validation_test": run_sets["validation"] & run_sets["test"],
    }
    if any(overlaps.values()):
        issues.append(f"run leakage detected: {overlaps}")
    for split, frame in splits.items():
        unavailable = frame["thermal_state"].isna().sum()
        if unavailable:
            issues.append(f"{split} contains {unavailable} unavailable targets")
        numeric = frame[feature_columns].select_dtypes(include=[np.number])
        if np.isinf(numeric.to_numpy()).any():
            issues.append(f"{split} contains infinite feature values")
    return issues


def _feature_summary(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    finite = _finite_numeric_frame(frame, columns)
    summary = finite.agg(["min", "max", "mean", "std"]).T.reset_index()
    return summary.rename(columns={"index": "feature"})


def _class_by_split(splits: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for split, frame in splits.items():
        counts = frame["thermal_state"].value_counts(dropna=False)
        for state, count in counts.items():
            rows.append({"split": split, "thermal_state": state, "row_count": count})
    return pd.DataFrame(rows)


def _class_by_scenario(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(["scenario", "thermal_state"], dropna=False)
        .size()
        .reset_index(name="row_count")
    )


def _duplicate_timestamps(frame: pd.DataFrame) -> int:
    return int(frame.duplicated(["run_id", "timestamp"]).sum())


def _near_constant(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    near_constant = []
    finite = _finite_numeric_frame(frame, columns)
    for column in finite.columns:
        series = finite[column].dropna()
        if not series.empty and series.std() <= 1e-9:
            near_constant.append(column)
    return near_constant


def _highly_correlated(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    corr = _finite_numeric_frame(frame, columns).corr(numeric_only=True).abs()
    pairs = []
    for left_index, left in enumerate(corr.columns):
        for right in corr.columns[left_index + 1 :]:
            value = corr.loc[left, right]
            if pd.notna(value) and value >= 0.98:
                pairs.append(
                    {"feature_a": left, "feature_b": right, "correlation": value}
                )
    return pairs


def _infinite_features(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    numeric = frame[columns].select_dtypes(include=[np.number])
    return [col for col in numeric if np.isinf(numeric[col].to_numpy()).any()]


def _nan_features(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [col for col in columns if frame[col].isna().any()]


def _finite_numeric_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    numeric = frame[columns].select_dtypes(include=[np.number]).copy()
    return numeric.replace([np.inf, -np.inf], np.nan)


def _count_dict(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.value_counts(dropna=False).items()}


def _health_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Dataset Health Report",
        "",
        f"Status: `{report['status']}`",
        f"Total rows: {report['total_rows']}",
        f"Total runs: {report['total_runs']}",
        "",
        "## Issues",
        "",
    ]
    lines.extend(f"- {issue}" for issue in report["issues"] or ["None"])
    lines.extend(["", "## Rows By Thermal State", ""])
    lines.extend(
        f"- {state}: {count}"
        for state, count in sorted(report["rows_by_thermal_state"].items())
    )
    lines.append("\nSynthetic metrics are simulated results, not hardware results.\n")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run dataset health audit CLI."""

    parser = argparse.ArgumentParser(
        description="Analyze Thermal Nexus dataset health."
    )
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        report = analyze_dataset_health(args.train, args.validation, args.test)
    except DatasetHealthError as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Dataset health passed for %s rows.", report["total_rows"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
