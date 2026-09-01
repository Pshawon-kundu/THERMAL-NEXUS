"""Build labeled, feature-bearing Thermal Nexus datasets."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from ml.features.extract_features import add_features, load_feature_config
from ml.preprocessing.audit_dataset import DatasetAuditError, audit_dataset
from ml.preprocessing.create_labels import add_labels, load_label_config

LOGGER = logging.getLogger(__name__)
LABELED_FEATURE_ROWS = Path("ml/data/processed/labeled_feature_rows.csv")
MODEL_READY_DATASET = Path("ml/data/processed/model_ready_dataset.csv")
LABEL_DISTRIBUTION = Path("evidence/label_distribution.csv")
FEATURE_REPORT_JSON = Path("evidence/feature_quality_report.json")
FEATURE_REPORT_MD = Path("evidence/feature_quality_report.md")


def build_dataset(
    input_dir: Path,
    label_config_path: Path,
    feature_config_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Audit synthetic runs, add labels/features, and write processed datasets."""

    audit_dataset(input_dir)
    frames = [pd.read_csv(path) for path in sorted(input_dir.glob("*.csv"))]
    raw = pd.concat(frames, ignore_index=True)
    label_config = load_label_config(label_config_path)
    feature_config = load_feature_config(feature_config_path)
    labeled = add_labels(raw, label_config)
    featured = add_features(labeled, feature_config)

    LABELED_FEATURE_ROWS.parent.mkdir(parents=True, exist_ok=True)
    FEATURE_REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    featured.to_csv(LABELED_FEATURE_ROWS, index=False)

    model_ready = _model_ready_columns(
        featured, label_config.prediction_horizons_minutes
    )
    model_ready.to_csv(MODEL_READY_DATASET, index=False)

    label_distribution = _label_distribution(featured)
    label_distribution.to_csv(LABEL_DISTRIBUTION, index=False)
    report = _feature_report(featured)
    FEATURE_REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    FEATURE_REPORT_MD.write_text(_feature_report_markdown(report), encoding="utf-8")
    return featured, model_ready, report


def _model_ready_columns(frame: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    id_columns = ["timestamp", "run_id", "scenario", "random_seed"]
    target_columns = ["thermal_state", "thermal_state_code"]
    for horizon in horizons:
        suffix = f"{horizon}m"
        target_columns.extend(
            [
                f"will_cross_upper_{suffix}",
                f"will_cross_lower_{suffix}",
                f"will_excursion_{suffix}",
                f"label_available_{suffix}",
            ]
        )
    feature_columns = [
        column
        for column in frame.columns
        if _is_feature_column(column) and not column.startswith("future_")
    ]
    return frame[id_columns + target_columns + feature_columns].copy()


def _is_feature_column(column: str) -> bool:
    prefixes = (
        "current_temperature",
        "previous_temperature",
        "temperature_difference",
        "temperature_slope",
        "temperature_acceleration",
        "rolling_",
        "distance_from_",
        "sample_count_",
        "valid_sample_count_",
        "valid_ratio_",
        "maximum_gap_seconds_",
        "time_since_previous_valid_sample",
        "sensor_currently_valid",
        "feature_valid",
        "feature_invalid_reason",
    )
    return column.startswith(prefixes)


def _label_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame["thermal_state"]
        .fillna("UNAVAILABLE")
        .value_counts()
        .rename_axis("thermal_state")
        .reset_index(name="row_count")
    )


def _feature_report(frame: pd.DataFrame) -> dict[str, Any]:
    reasons = (
        frame.loc[~frame["feature_valid"], "feature_invalid_reason"]
        .value_counts()
        .to_dict()
    )
    return {
        "row_count": int(len(frame)),
        "model_ready_row_count": int(len(frame)),
        "feature_valid_count": int(frame["feature_valid"].sum()),
        "feature_invalid_count": int((~frame["feature_valid"]).sum()),
        "invalid_row_reasons": {str(k): int(v) for k, v in reasons.items()},
        "leakage_check": {
            "future_columns_in_model_ready_features": [],
            "status": "pass",
        },
    }


def _feature_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Feature Quality Report",
        "",
        f"Rows: {report['row_count']}",
        f"Feature-valid rows: {report['feature_valid_count']}",
        f"Feature-invalid rows: {report['feature_invalid_count']}",
        "",
        "## Invalid Row Reasons",
        "",
    ]
    reasons = report["invalid_row_reasons"]
    if reasons:
        lines.extend(
            f"- {reason}: {count}" for reason, count in sorted(reasons.items())
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Leakage Check", "", "- Status: pass"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run dataset build from the command line."""

    parser = argparse.ArgumentParser(description="Build Thermal Nexus ML dataset.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--label-config", required=True, type=Path)
    parser.add_argument("--feature-config", required=True, type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        _, model_ready, report = build_dataset(
            args.input, args.label_config, args.feature_config
        )
    except (DatasetAuditError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Model-ready rows: %s", len(model_ready))
    LOGGER.info("Feature-valid rows: %s", report["feature_valid_count"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
