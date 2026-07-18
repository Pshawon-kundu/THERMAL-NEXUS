"""Evaluate Thermal Nexus baselines on train/validation/test splits."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache")))

import matplotlib
import pandas as pd
import yaml

from ml.baselines.fixed_threshold import FixedThresholdConfig, predict_fixed_threshold
from ml.baselines.rule_based import load_rule_config, predict_rule_based
from ml.evaluation.baseline_metrics import CLASSES, evaluate_predictions

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LOGGER = logging.getLogger(__name__)
OUT_DIR = Path("evidence/baselines")
PLOT_DIR = OUT_DIR / "plots"


def evaluate_baselines(
    train_path: Path,
    validation_path: Path,
    test_path: Path,
    config_path: Path,
    output_dir: Path = OUT_DIR,
) -> dict[str, Any]:
    """Evaluate fixed-threshold and rule-based baselines."""

    datasets = {
        "train": pd.read_csv(train_path),
        "validation": pd.read_csv(validation_path),
        "test": pd.read_csv(test_path),
    }
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    fixed_config = FixedThresholdConfig(
        lower_limit_c=float(raw_config["fixed_threshold"]["lower_limit_c"]),
        upper_limit_c=float(raw_config["fixed_threshold"]["upper_limit_c"]),
    )
    rule_config = load_rule_config(config_path)
    plot_dir = output_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {"fixed_threshold": {}, "rule_based": {}}
    predictions: dict[str, dict[str, pd.DataFrame]] = {
        "fixed_threshold": {},
        "rule_based": {},
    }
    for split, frame in datasets.items():
        fixed_pred = predict_fixed_threshold(frame, fixed_config)
        rule_pred = predict_rule_based(frame, rule_config)
        predictions["fixed_threshold"][split] = fixed_pred
        predictions["rule_based"][split] = rule_pred
        results["fixed_threshold"][split] = evaluate_predictions(frame, fixed_pred)
        results["rule_based"][split] = evaluate_predictions(frame, rule_pred)

    _write_json(output_dir / "fixed_threshold_metrics.json", results["fixed_threshold"])
    _write_json(output_dir / "rule_based_metrics.json", results["rule_based"])
    comparison = _comparison(results)
    comparison.to_csv(output_dir / "baseline_comparison.csv", index=False)
    (output_dir / "baseline_report.md").write_text(
        _report_markdown(results, comparison), encoding="utf-8"
    )
    _plots(results, datasets, predictions, plot_dir)
    return results


def _comparison(results: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for baseline, split_metrics in results.items():
        for split, metrics in split_metrics.items():
            rows.append(
                {
                    "baseline": baseline,
                    "split": split,
                    "macro_f1": metrics["macro_f1"],
                    "weighted_f1": metrics["weighted_f1"],
                    "balanced_accuracy": metrics["balanced_accuracy"],
                    "false_alarm_rate": metrics["false_alarm_rate"],
                    "missed_event_rate": metrics["missed_event_rate"],
                    "median_warning_lead_time_seconds": metrics[
                        "median_warning_lead_time_seconds"
                    ],
                    "mean_warning_lead_time_seconds": metrics[
                        "mean_warning_lead_time_seconds"
                    ],
                    "alerts": metrics["number_of_alerts"],
                    "missed_excursions": metrics["number_of_missed_excursions"],
                }
            )
    return pd.DataFrame(rows)


def _plots(
    results: dict[str, Any],
    datasets: dict[str, pd.DataFrame],
    predictions: dict[str, dict[str, pd.DataFrame]],
    plot_dir: Path,
) -> None:
    for baseline, split_metrics in results.items():
        for split, metrics in split_metrics.items():
            matrix = pd.DataFrame(metrics["confusion_matrix"]).reindex(
                index=CLASSES, columns=CLASSES, fill_value=0
            )
            fig, axis = plt.subplots(figsize=(5, 4))
            image = axis.imshow(matrix.values, cmap="Blues")
            axis.set_xticks(range(len(CLASSES)), CLASSES, rotation=45, ha="right")
            axis.set_yticks(range(len(CLASSES)), CLASSES)
            axis.set_title(f"{baseline} {split} confusion matrix")
            for i in range(len(CLASSES)):
                for j in range(len(CLASSES)):
                    axis.text(j, i, int(matrix.iloc[i, j]), ha="center", va="center")
            fig.colorbar(image, ax=axis)
            fig.tight_layout()
            fig.savefig(plot_dir / f"{baseline}_{split}_confusion_matrix.png", dpi=140)
            plt.close(fig)
    comparison = _comparison(results)
    _bar_plot(comparison, "macro_f1", "precision_recall_f1_comparison.png", plot_dir)
    _bar_plot(
        comparison,
        "median_warning_lead_time_seconds",
        "warning_lead_time.png",
        plot_dir,
    )
    _bar_plot(comparison, "false_alarm_rate", "false_alarm_comparison.png", plot_dir)
    _bar_plot(comparison, "missed_event_rate", "missed_event_comparison.png", plot_dir)
    _example_timeline(datasets["test"], predictions["rule_based"]["test"], plot_dir)


def _bar_plot(frame: pd.DataFrame, metric: str, name: str, plot_dir: Path) -> None:
    fig, axis = plt.subplots(figsize=(8, 4))
    labels = frame["baseline"] + "\n" + frame["split"]
    axis.bar(labels, frame[metric].fillna(0))
    axis.set_title(metric)
    axis.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    fig.savefig(plot_dir / name, dpi=140)
    plt.close(fig)


def _example_timeline(
    frame: pd.DataFrame, prediction: pd.DataFrame, plot_dir: Path
) -> None:
    run_id = frame["run_id"].iloc[0]
    run = frame[frame["run_id"] == run_id].merge(prediction, on=["timestamp", "run_id"])
    times = pd.to_datetime(run["timestamp"], utc=True)
    fig, axis = plt.subplots(figsize=(9, 4))
    axis.plot(times, run["current_temperature"], label="measured")
    axis.step(times, run["thermal_state_code"], label="true state", where="post")
    axis.step(times, run["predicted_state_code"], label="predicted", where="post")
    axis.set_title(f"Example prediction timeline: {run_id}")
    axis.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(plot_dir / "example_prediction_timeline.png", dpi=140)
    plt.close(fig)


def _report_markdown(results: dict[str, Any], comparison: pd.DataFrame) -> str:
    lines = [
        "# Baseline Report",
        "",
        "Metrics are simulated software-only results from synthetic data.",
        "No learned model was trained.",
        "",
        "## Comparison",
        "",
        _markdown_table(comparison),
        "",
    ]
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append("" if pd.isna(value) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run baseline evaluation command."""

    parser = argparse.ArgumentParser(description="Evaluate Thermal Nexus baselines.")
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    evaluate_baselines(args.train, args.validation, args.test, args.config)
    LOGGER.info("Baseline evaluation written to %s", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
