"""Run-level train/validation/test splitting."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

LOGGER = logging.getLogger(__name__)


class SplitError(ValueError):
    """Raised when run-level splitting fails."""


def split_dataset(
    input_path: Path,
    output_dir: Path,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> dict[str, Any]:
    """Split a model-ready dataset by whole run_id values."""

    if round(train_ratio + validation_ratio + test_ratio, 6) != 1.0:
        raise SplitError("Split ratios must sum to 1.0.")
    frame = _filter_available_targets(pd.read_csv(input_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    assignments = _assign_runs(frame, train_ratio, validation_ratio)

    split_frames = {}
    for split_name in ["train", "validation", "test"]:
        run_ids = assignments.loc[assignments["split"] == split_name, "run_id"]
        split_frame = frame[frame["run_id"].isin(run_ids)].copy()
        split_frame.to_csv(output_dir / f"{split_name}.csv", index=False)
        split_frames[split_name] = split_frame

    assignments.to_csv(output_dir / "split_manifest.csv", index=False)
    report = _validate_split(frame, split_frames, assignments)
    (Path("evidence") / "split_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (Path("evidence") / "split_report.md").write_text(
        _split_report_markdown(report), encoding="utf-8"
    )
    if report["status"] != "pass":
        raise SplitError("Split validation failed.")
    return report


def _filter_available_targets(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep rows with available primary targets for model/evaluation splits."""

    if "label_available_10m" not in frame.columns:
        return frame
    available = frame["label_available_10m"].astype(str).str.lower().isin({"true", "1"})
    return frame[available & frame["thermal_state"].notna()].copy()


def _assign_runs(
    frame: pd.DataFrame, train_ratio: float, validation_ratio: float
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for scenario, scenario_frame in frame.groupby("scenario"):
        run_ids = sorted(scenario_frame["run_id"].unique(), key=_stable_hash)
        count = len(run_ids)
        train_count = round(count * train_ratio)
        validation_count = round(count * validation_ratio)
        if count >= 3:
            train_count = min(max(train_count, 1), count - 2)
            validation_count = max(validation_count, 1)
        for index, run_id in enumerate(run_ids):
            if index < train_count:
                split = "train"
            elif index < train_count + validation_count:
                split = "validation"
            else:
                split = "test"
            rows.append({"run_id": run_id, "scenario": scenario, "split": split})
    return pd.DataFrame(rows).sort_values(["scenario", "split", "run_id"])


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_split(
    frame: pd.DataFrame,
    split_frames: dict[str, pd.DataFrame],
    assignments: pd.DataFrame,
) -> dict[str, Any]:
    original_runs = set(frame["run_id"].unique())
    assigned_runs = set(assignments["run_id"])
    split_run_sets = {
        name: set(split_frame["run_id"].unique())
        for name, split_frame in split_frames.items()
    }
    overlaps = {
        "train_validation": sorted(
            split_run_sets["train"] & split_run_sets["validation"]
        ),
        "train_test": sorted(split_run_sets["train"] & split_run_sets["test"]),
        "validation_test": sorted(
            split_run_sets["validation"] & split_run_sets["test"]
        ),
    }
    divided_runs = []
    for run_id, group in pd.concat(split_frames, names=["split"]).groupby("run_id"):
        if group.index.get_level_values("split").nunique() > 1:
            divided_runs.append(run_id)

    split_run_counts = {name: len(runs) for name, runs in split_run_sets.items()}
    return {
        "status": (
            "pass"
            if original_runs == assigned_runs
            and not any(overlaps.values())
            and not divided_runs
            else "fail"
        ),
        "input_rows": int(len(frame)),
        "input_runs": int(len(original_runs)),
        "split_run_counts": split_run_counts,
        "split_row_counts": {
            name: int(len(split_frame)) for name, split_frame in split_frames.items()
        },
        "overlaps": overlaps,
        "divided_runs": sorted(divided_runs),
        "missing_runs": sorted(original_runs - assigned_runs),
        "extra_runs": sorted(assigned_runs - original_runs),
        "deterministic_method": "scenario group + sha256(run_id) ordering",
    }


def _split_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Split Report",
        "",
        f"Status: `{report['status']}`",
        f"Input runs: {report['input_runs']}",
        f"Input rows: {report['input_rows']}",
        "",
        "## Run Counts",
        "",
    ]
    lines.extend(
        f"- {split}: {count}"
        for split, count in sorted(report["split_run_counts"].items())
    )
    lines.extend(["", "## Overlap Check", ""])
    if any(report["overlaps"].values()):
        lines.extend(f"- {name}: {runs}" for name, runs in report["overlaps"].items())
    else:
        lines.append("- Zero run overlap confirmed.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run split command."""

    parser = argparse.ArgumentParser(description="Split Thermal Nexus dataset by run.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        report = split_dataset(args.input, args.output)
    except SplitError as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Split passed: %s", report["split_run_counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
