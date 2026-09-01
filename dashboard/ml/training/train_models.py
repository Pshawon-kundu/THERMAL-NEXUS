"""Train lightweight supervised Thermal Nexus candidate models."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache")))

import joblib
import matplotlib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from ml.baselines.fixed_threshold import FixedThresholdConfig, predict_fixed_threshold
from ml.baselines.rule_based import load_rule_config, predict_rule_based
from ml.evaluation.model_metrics import (
    CLASSES,
    artifact_size_bytes,
    evaluate_model_predictions,
    measure_latency_ms,
)
from ml.training.data_loader import SplitData, load_split, verify_zero_split_overlap
from ml.training.group_cv import make_group_folds, write_group_cv_report
from ml.training.training_schema import TrainingSchema, load_training_schema

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LOGGER = logging.getLogger(__name__)


def train_candidates(config_path: Path) -> dict[str, Any]:
    """Train candidates, select by validation metrics, and write artifacts."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    seed = int(config["random_seed"])
    train_path = Path("ml/data/splits/train.csv")
    validation_path = Path("ml/data/splits/validation.csv")
    train_frame = pd.read_csv(train_path)
    schema = load_training_schema(config_path, train_frame)
    splits = {
        "train": load_split(train_path, schema),
        "validation": load_split(validation_path, schema),
    }
    verify_zero_split_overlap(splits)

    evidence_dir = Path(config["artifacts"]["evidence_dir"])
    plots_dir = evidence_dir / "plots"
    candidates_dir = Path(config["artifacts"]["candidates_dir"])
    selected_dir = Path(config["artifacts"]["selected_dir"])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir.mkdir(parents=True, exist_ok=True)
    selected_dir.mkdir(parents=True, exist_ok=True)

    folds, cv_report = make_group_folds(
        splits["train"].features,
        splits["train"].target,
        splits["train"].groups,
        int(config["cross_validation"]["n_splits"]),
        seed,
    )
    write_group_cv_report(cv_report, evidence_dir)

    training_id = time.strftime("%Y%m%d_%H%M%S")
    class_mapping = {klass: index for index, klass in enumerate(CLASSES)}
    candidate_results: list[dict[str, Any]] = []

    for model_name in config["models"]:
        result = _train_one_model(
            model_name=model_name,
            config=config,
            schema=schema,
            splits=splits,
            folds=folds,
            seed=seed,
            training_id=training_id,
            candidates_dir=candidates_dir,
            class_mapping=class_mapping,
            config_path=config_path,
        )
        candidate_results.append(result)

    selected = _select_model(candidate_results, config["selection"])
    selected_version_dir = (
        selected_dir / f"provisional_{training_id}_{selected['model_name']}"
    )
    if selected_version_dir.exists():
        raise FileExistsError(
            f"Selected model directory already exists: {selected_version_dir}"
        )
    shutil.copytree(selected["artifact_dir"], selected_version_dir)
    (selected_dir / "latest_selected.json").write_text(
        json.dumps(
            {
                "selected_model": selected["model_name"],
                "artifact_dir": str(selected_version_dir),
                "selected_from_validation": True,
                "test_evaluated": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    comparison = pd.DataFrame(candidate_results)
    baseline_rows = _validation_baselines(splits["validation"])
    _write_reports(comparison, selected, evidence_dir, plots_dir, baseline_rows)
    LOGGER.info("Selected provisional model: %s", selected["model_name"])
    return {
        "selected": selected,
        "candidate_results": candidate_results,
        "group_cv": cv_report,
    }


def _train_one_model(
    model_name: str,
    config: dict[str, Any],
    schema: TrainingSchema,
    splits: dict[str, Any],
    folds: list[tuple[list[int], list[int]]],
    seed: int,
    training_id: str,
    candidates_dir: Path,
    class_mapping: dict[str, int],
    config_path: Path,
) -> dict[str, Any]:
    model_config = config["models"][model_name]
    search = _param_grid(model_name, model_config, seed)
    best_score = -np.inf
    best_params: dict[str, Any] = {}
    best_cv_metrics: dict[str, Any] = {}

    for params in search:
        fold_scores = []
        fold_metrics = []
        for train_idx, fold_idx in folds:
            estimator = _estimator(model_name, params, seed)
            pipeline = _pipeline(estimator, bool(model_config["scaler_required"]))
            pipeline.fit(
                splits["train"].features.iloc[train_idx],
                splits["train"].target.iloc[train_idx],
            )
            predicted = pd.Series(
                pipeline.predict(splits["train"].features.iloc[fold_idx])
            )
            metrics = evaluate_model_predictions(
                splits["train"].frame.iloc[fold_idx].reset_index(drop=True), predicted
            )
            fold_metrics.append(metrics)
            fold_scores.append(metrics["macro_f1"])
        score = float(np.mean(fold_scores))
        if score > best_score:
            best_score = score
            best_params = params
            best_cv_metrics = {
                "mean_macro_f1": score,
                "fold_macro_f1": fold_scores,
                "fold_metrics": fold_metrics,
            }

    final_estimator = _estimator(model_name, best_params, seed)
    final_pipeline = _pipeline(final_estimator, bool(model_config["scaler_required"]))
    final_pipeline.fit(splits["train"].features, splits["train"].target)
    validation_pred = pd.Series(final_pipeline.predict(splits["validation"].features))
    probabilities = (
        final_pipeline.predict_proba(splits["validation"].features)
        if hasattr(final_pipeline, "predict_proba")
        else None
    )
    metrics = evaluate_model_predictions(
        splits["validation"].frame.reset_index(drop=True),
        validation_pred,
        probabilities,
    )
    latency = measure_latency_ms(final_pipeline, splits["validation"].features)
    complexity = _model_complexity(model_name, final_pipeline)

    artifact_dir = candidates_dir / model_name / training_id
    if artifact_dir.exists():
        raise FileExistsError(f"Candidate artifact directory exists: {artifact_dir}")
    artifact_dir.mkdir(parents=True)
    joblib.dump(final_pipeline, artifact_dir / "pipeline.joblib")
    joblib.dump(final_pipeline, artifact_dir / "model.joblib")
    joblib.dump(final_pipeline[:-1], artifact_dir / "preprocessing.joblib")
    _write_yaml(
        artifact_dir / "configuration.yaml", {"model": model_name, **best_params}
    )
    _write_json(
        artifact_dir / "feature_schema.json", {"features": schema.feature_columns}
    )
    _write_json(artifact_dir / "class_mapping.json", class_mapping)

    artifact_files = [
        artifact_dir / "pipeline.joblib",
        artifact_dir / "model.joblib",
        artifact_dir / "preprocessing.joblib",
    ]
    size_bytes = artifact_size_bytes(artifact_files)
    metrics.update(
        {
            "model_name": model_name,
            "best_params": best_params,
            "cross_validation": best_cv_metrics,
            "model_file_size_bytes": (artifact_dir / "model.joblib").stat().st_size,
            "preprocessing_artifact_size_bytes": (artifact_dir / "preprocessing.joblib")
            .stat()
            .st_size,
            "total_artifact_size_bytes": size_bytes,
            "training_timestamp": training_id,
            "source_git_commit": _git_commit(),
            **latency,
            **complexity,
        }
    )
    _write_json(artifact_dir / "metrics_validation.json", metrics)
    _write_json(artifact_dir / "checksums.json", _checksums(artifact_dir))
    (artifact_dir / "MODEL_CARD.md").write_text(
        _model_card(model_name, metrics, model_config), encoding="utf-8"
    )
    return _summary_row(model_name, metrics, artifact_dir, model_config)


def _param_grid(
    model_name: str, model_config: dict[str, Any], seed: int
) -> list[dict[str, Any]]:
    if model_name == "logistic_regression":
        return [
            {"C": c, "class_weight": cw}
            for c, cw in itertools.product(
                model_config["C"], model_config["class_weight"]
            )
        ]
    if model_name == "decision_tree":
        keys = [
            "max_depth",
            "min_samples_leaf",
            "min_samples_split",
            "ccp_alpha",
            "class_weight",
        ]
        return [
            dict(zip(keys, values, strict=True))
            for values in itertools.product(*(model_config[k] for k in keys))
        ]
    if model_name == "random_forest_reference":
        keys = [
            "n_estimators",
            "max_depth",
            "min_samples_leaf",
            "max_features",
            "class_weight",
        ]
        return [
            dict(zip(keys, values, strict=True))
            for values in itertools.product(*(model_config[k] for k in keys))
        ]
    if model_name == "small_mlp":
        return [
            {"hidden_layer_sizes": tuple(hidden), "alpha": alpha}
            for hidden, alpha in itertools.product(
                model_config["hidden_layer_sizes"], model_config["alpha"]
            )
        ]
    raise ValueError(f"Unsupported model: {model_name}")


def _estimator(model_name: str, params: dict[str, Any], seed: int) -> object:
    if model_name == "logistic_regression":
        return LogisticRegression(
            C=float(params["C"]),
            class_weight=params["class_weight"],
            max_iter=300,
            solver="lbfgs",
            random_state=seed,
        )
    if model_name == "decision_tree":
        return DecisionTreeClassifier(random_state=seed, **params)
    if model_name == "random_forest_reference":
        return RandomForestClassifier(random_state=seed, n_jobs=1, **params)
    if model_name == "small_mlp":
        return MLPClassifier(
            hidden_layer_sizes=params["hidden_layer_sizes"],
            alpha=float(params["alpha"]),
            early_stopping=True,
            max_iter=300,
            random_state=seed,
        )
    raise ValueError(f"Unsupported model: {model_name}")


def _pipeline(estimator: object, scale: bool) -> Pipeline:
    steps = []
    if scale:
        steps.append(("scaler", StandardScaler()))
    steps.append(("model", estimator))
    return Pipeline(steps)


def _select_model(
    rows: list[dict[str, Any]], selection_config: dict[str, Any]
) -> dict[str, Any]:
    eligible = []
    for row in rows:
        risk_recall = row["excursion_risk_recall"]
        missed = row["missed_event_rate"]
        row["rejected"] = bool(
            risk_recall < float(selection_config["minimum_excursion_recall"])
            or missed > float(selection_config["maximum_missed_event_rate"])
        )
        row["selection_score"] = _selection_score(
            row, selection_config["metric_weights"]
        )
        if not row["rejected"]:
            eligible.append(row)
    deployable = [
        row
        for row in eligible
        if "REFERENCE_MODEL_NOT_YET_APPROVED" not in row["deployment_suitability"]
    ]
    candidates = deployable or eligible or rows
    return sorted(
        candidates,
        key=lambda row: (
            row["selection_score"],
            -row["total_artifact_size_bytes"],
            -row["mean_inference_latency_ms"],
        ),
        reverse=True,
    )[0]


def _selection_score(row: dict[str, Any], weights: dict[str, float]) -> float:
    return float(
        row["excursion_risk_recall"] * weights["excursion_recall"]
        + row["missed_event_rate"] * weights["missed_event_rate"]
        + (row["median_warning_lead_time_seconds"] or 0.0)
        * weights["median_warning_lead_time_seconds"]
        + row["macro_f1"] * weights["macro_f1"]
        + row["transition_recall"] * weights["transition_recall"]
        + row["false_alarm_rate"] * weights["false_alarm_rate"]
        + row["total_artifact_size_bytes"] / 1_000_000.0 * weights["artifact_size_mb"]
        + row["mean_inference_latency_ms"] * weights["mean_latency_ms"]
    )


def _summary_row(
    model_name: str,
    metrics: dict[str, Any],
    artifact_dir: Path,
    model_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "model_type": model_name,
        "macro_f1": metrics["macro_f1"],
        "weighted_f1": metrics["weighted_f1"],
        "balanced_accuracy": metrics["balanced_accuracy"],
        "excursion_risk_recall": metrics["per_class"]["EXCURSION_RISK"]["recall"],
        "transition_recall": metrics["per_class"]["TRANSITION"]["recall"],
        "false_alarm_rate": metrics["false_alarm_rate"],
        "missed_event_rate": metrics["missed_event_rate"],
        "mean_warning_lead_time_seconds": metrics["mean_warning_lead_time_seconds"],
        "median_warning_lead_time_seconds": metrics["median_warning_lead_time_seconds"],
        "total_artifact_size_bytes": metrics["total_artifact_size_bytes"],
        "mean_inference_latency_ms": metrics["mean_inference_latency_ms"],
        "p95_inference_latency_ms": metrics["p95_inference_latency_ms"],
        "deployment_suitability": model_config.get(
            "deployment_label", "provisional_candidate"
        ),
        "artifact_dir": str(artifact_dir),
    }


def _write_reports(
    comparison: pd.DataFrame,
    selected: dict[str, Any],
    evidence_dir: Path,
    plots_dir: Path,
    baseline_rows: pd.DataFrame,
) -> None:
    combined = pd.concat([comparison, baseline_rows], ignore_index=True)
    combined.to_csv(evidence_dir / "model_comparison.csv", index=False)
    (evidence_dir / "model_comparison.md").write_text(
        _markdown_table(combined), encoding="utf-8"
    )
    _write_json(
        evidence_dir / "validation_metrics.json",
        comparison.to_dict(orient="records"),
    )
    (evidence_dir / "model_selection_report.md").write_text(
        "# Model Selection Report\n\n"
        "Results are preliminary synthetic software results.\n\n"
        f"Selected provisional model: `{selected['model_name']}`\n\n"
        f"Selection score: `{selected['selection_score']:.4f}`\n",
        encoding="utf-8",
    )
    comparison[["model_name", "total_artifact_size_bytes"]].to_csv(
        evidence_dir / "artifact_size_report.csv", index=False
    )
    comparison[
        ["model_name", "mean_inference_latency_ms", "p95_inference_latency_ms"]
    ].to_csv(evidence_dir / "inference_latency_report.csv", index=False)
    _comparison_plots(comparison, plots_dir)
    _candidate_detail_plots(comparison, plots_dir)


def _validation_baselines(validation: SplitData) -> pd.DataFrame:
    from ml.evaluation.baseline_metrics import evaluate_predictions

    baselines_config = yaml.safe_load(
        Path("config/baselines.yaml").read_text(encoding="utf-8")
    )
    fixed_config = FixedThresholdConfig(
        lower_limit_c=float(baselines_config["fixed_threshold"]["lower_limit_c"]),
        upper_limit_c=float(baselines_config["fixed_threshold"]["upper_limit_c"]),
    )
    fixed_metrics = evaluate_predictions(
        validation.frame, predict_fixed_threshold(validation.frame, fixed_config)
    )
    rule_metrics = evaluate_predictions(
        validation.frame,
        predict_rule_based(
            validation.frame, load_rule_config(Path("config/baselines.yaml"))
        ),
    )
    rows = []
    for name, metrics in {
        "fixed_threshold": fixed_metrics,
        "rule_based": rule_metrics,
    }.items():
        rows.append(
            {
                "model_name": name,
                "model_type": "baseline",
                "macro_f1": metrics["macro_f1"],
                "weighted_f1": metrics["weighted_f1"],
                "balanced_accuracy": metrics["balanced_accuracy"],
                "excursion_risk_recall": metrics["per_class"]["EXCURSION_RISK"][
                    "recall"
                ],
                "transition_recall": metrics["per_class"]["TRANSITION"]["recall"],
                "false_alarm_rate": metrics["false_alarm_rate"],
                "missed_event_rate": metrics["missed_event_rate"],
                "mean_warning_lead_time_seconds": metrics[
                    "mean_warning_lead_time_seconds"
                ],
                "median_warning_lead_time_seconds": metrics[
                    "median_warning_lead_time_seconds"
                ],
                "total_artifact_size_bytes": 0,
                "mean_inference_latency_ms": np.nan,
                "p95_inference_latency_ms": np.nan,
                "deployment_suitability": "baseline_comparison",
                "artifact_dir": "",
                "rejected": False,
                "selection_score": np.nan,
            }
        )
    return pd.DataFrame(rows)


def _comparison_plots(comparison: pd.DataFrame, plots_dir: Path) -> None:
    metrics = {
        "macro_f1": "macro_f1_comparison.png",
        "excursion_risk_recall": "excursion_risk_recall_comparison.png",
        "transition_recall": "transition_recall_comparison.png",
        "false_alarm_rate": "false_alarm_comparison.png",
        "missed_event_rate": "missed_event_comparison.png",
        "median_warning_lead_time_seconds": "warning_lead_time_comparison.png",
        "total_artifact_size_bytes": "artifact_size_comparison.png",
        "mean_inference_latency_ms": "inference_latency_comparison.png",
    }
    for metric, filename in metrics.items():
        fig, axis = plt.subplots(figsize=(8, 4))
        axis.bar(comparison["model_name"], comparison[metric].fillna(0))
        axis.set_title(metric)
        axis.tick_params(axis="x", labelrotation=30)
        fig.tight_layout()
        fig.savefig(plots_dir / filename, dpi=140)
        plt.close(fig)


def _candidate_detail_plots(comparison: pd.DataFrame, plots_dir: Path) -> None:
    for _, row in comparison.iterrows():
        artifact_dir = Path(str(row["artifact_dir"]))
        metrics_path = artifact_dir / "metrics_validation.json"
        if not metrics_path.exists():
            continue
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        matrix = pd.DataFrame(metrics["confusion_matrix"]).reindex(
            index=CLASSES, columns=CLASSES, fill_value=0
        )
        fig, axis = plt.subplots(figsize=(5, 4))
        axis.imshow(matrix.values, cmap="Blues")
        axis.set_xticks(range(len(CLASSES)), CLASSES, rotation=35, ha="right")
        axis.set_yticks(range(len(CLASSES)), CLASSES)
        axis.set_title(f"{row['model_name']} validation confusion")
        for i in range(len(CLASSES)):
            for j in range(len(CLASSES)):
                axis.text(j, i, str(int(matrix.iloc[i, j])), ha="center", va="center")
        fig.tight_layout()
        fig.savefig(plots_dir / f"{row['model_name']}_confusion_matrix.png", dpi=140)
        plt.close(fig)
        if "probability_calibration_summary" in metrics:
            fig, axis = plt.subplots(figsize=(5, 4))
            values = list(metrics["probability_calibration_summary"].values())
            labels = list(metrics["probability_calibration_summary"].keys())
            axis.bar(labels, values)
            axis.set_title(f"{row['model_name']} probability summary")
            axis.tick_params(axis="x", labelrotation=25)
            fig.tight_layout()
            fig.savefig(
                plots_dir / f"{row['model_name']}_probability_summary.png", dpi=140
            )
            plt.close(fig)
        if "feature_importance" in metrics:
            importance = pd.Series(metrics["feature_importance"]).sort_values().tail(12)
            fig, axis = plt.subplots(figsize=(7, 5))
            importance.plot(kind="barh", ax=axis)
            axis.set_title(f"{row['model_name']} feature importance")
            fig.tight_layout()
            fig.savefig(
                plots_dir / f"{row['model_name']}_feature_importance.png", dpi=140
            )
            plt.close(fig)


def _model_complexity(model_name: str, pipeline: Pipeline) -> dict[str, Any]:
    model = pipeline.named_steps["model"]
    if model_name == "decision_tree":
        return {
            "tree_depth": int(model.get_depth()),
            "tree_leaves": int(model.get_n_leaves()),
            "tree_nodes": int(model.tree_.node_count),
            "feature_importance": _feature_importance(pipeline),
        }
    if model_name == "random_forest_reference":
        return {
            "tree_count": int(len(model.estimators_)),
            "feature_importance": _feature_importance(pipeline),
            "reference_label": (
                "REFERENCE_MODEL_NOT_YET_APPROVED_FOR_EMBEDDED_DEPLOYMENT"
            ),
        }
    if model_name == "small_mlp":
        coeff_count = int(
            sum(coef.size for coef in model.coefs_)
            + sum(b.size for b in model.intercepts_)
        )
        return {
            "converged": bool(model.n_iter_ < model.max_iter),
            "iterations": int(model.n_iter_),
            "trainable_parameter_count": coeff_count,
            "loss_curve": [float(value) for value in getattr(model, "loss_curve_", [])],
        }
    if model_name == "logistic_regression":
        return {"coefficient_count": int(model.coef_.size + model.intercept_.size)}
    return {}


def _feature_importance(pipeline: Pipeline) -> dict[str, float]:
    model = pipeline.named_steps["model"]
    columns = pipeline.feature_names_in_
    return {
        str(column): float(value)
        for column, value in zip(columns, model.feature_importances_, strict=True)
    }


def _checksums(directory: Path) -> dict[str, str]:
    checksums = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "checksums.json":
            checksums[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return checksums


def _model_card(
    model_name: str, metrics: dict[str, Any], model_config: dict[str, Any]
) -> str:
    risk_recall = metrics["per_class"]["EXCURSION_RISK"]["recall"]
    deployment_note = model_config.get("deployment_label", "provisional_candidate")
    return (
        f"# {model_name}\n\n"
        "Preliminary synthetic software result. Not a hardware result.\n\n"
        f"Macro F1: {metrics['macro_f1']:.4f}\n"
        f"EXCURSION_RISK recall: {risk_recall:.4f}\n"
        f"Missed-event rate: {metrics['missed_event_rate']:.4f}\n"
        f"Deployment note: {deployment_note}\n"
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_yaml(path: Path, payload: object) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip()


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
            values.append(f"{value:.4f}" if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run candidate training without touching test.csv."""

    parser = argparse.ArgumentParser(
        description="Train Thermal Nexus candidate models."
    )
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    train_candidates(args.config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
