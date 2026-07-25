"""Baselines, models, and reports for the external T15 benchmark."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache")))

import joblib
import pandas as pd
from numpy.typing import ArrayLike
from sklearn.base import BaseEstimator, clone
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from ml.external_t15 import DATASET_LABEL
from ml.external_t15.paths import EVIDENCE_DIR, MODEL_READY_DIR
from ml.external_t15.schema import HORIZONS_MINUTES, SPLIT_ORDER


def train_external_models() -> dict[str, Any]:
    """Train baselines, regression models, and classification models."""

    data = _load_model_ready()
    _verify_split_contract(data)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    model_dir = MODEL_READY_DIR / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    group_report = EVIDENCE_DIR / "group_validation_report.csv"
    if group_report.exists():
        group_report.unlink()
    baseline_rows = _evaluate_regression_baselines(data["temperature_only"])
    regression_rows = _train_regression_models(data, model_dir)
    classification_rows = _train_classification_models(data, model_dir)
    _write_csv(EVIDENCE_DIR / "baseline_results.csv", baseline_rows)
    _write_csv(EVIDENCE_DIR / "regression_model_comparison.csv", regression_rows)
    _write_csv(
        EVIDENCE_DIR / "classification_model_comparison.csv", classification_rows
    )
    _write_training_metadata(data)
    return {
        "baseline_rows": len(baseline_rows),
        "regression_rows": len(regression_rows),
        "classification_rows": len(classification_rows),
    }


def evaluate_external_models() -> dict[str, Any]:
    """Evaluate locked test split and write benchmark report/plots."""

    data = _load_model_ready()
    baseline = pd.read_csv(EVIDENCE_DIR / "baseline_results.csv")
    regression = pd.read_csv(EVIDENCE_DIR / "regression_model_comparison.csv")
    classification = pd.read_csv(EVIDENCE_DIR / "classification_model_comparison.csv")
    _plot_metric(
        regression.loc[regression["split"] == "test"],
        "mae_c",
        EVIDENCE_DIR / "plots" / "test_regression_mae.png",
        "Locked Test Regression MAE",
    )
    _plot_metric(
        classification.loc[classification["split"] == "test"],
        "macro_f1",
        EVIDENCE_DIR / "plots" / "test_classification_macro_f1.png",
        "Locked Test Classification Macro F1",
    )
    best_regression = (
        regression.loc[regression["split"] == "test"]
        .sort_values(["horizon_minutes", "mae_c"])
        .groupby("horizon_minutes")
        .head(1)
    )
    best_classification = (
        classification.loc[classification["split"] == "test"]
        .sort_values("macro_f1", ascending=False)
        .head(1)
    )
    _write_benchmark_report(data, baseline, regression, classification)
    return {
        "locked_test_rows": int((data["temperature_only"]["split"] == "test").sum()),
        "best_regression": best_regression.to_dict(orient="records"),
        "best_classification": best_classification.to_dict(orient="records"),
    }


def verify_external_phase() -> dict[str, Any]:
    """Verify all required external benchmark outputs exist and are consistent."""

    required = [
        EVIDENCE_DIR / "DATASET_AUDIT.md",
        EVIDENCE_DIR / "EDA_REPORT.md",
        EVIDENCE_DIR / "baseline_results.csv",
        EVIDENCE_DIR / "regression_model_comparison.csv",
        EVIDENCE_DIR / "classification_model_comparison.csv",
        EVIDENCE_DIR / "EXTERNAL_BENCHMARK_REPORT.md",
        EVIDENCE_DIR / "limitations.json",
        MODEL_READY_DIR / "temperature_only_benchmark.csv",
        MODEL_READY_DIR / "multivariate_research_reference.csv",
        MODEL_READY_DIR / "schema.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing external T15 outputs: {missing}")
    data = _load_model_ready()
    _verify_split_contract(data)
    for name, frame in data.items():
        labels = set(frame["data_source_type"])
        if labels != {DATASET_LABEL}:
            raise ValueError(f"{name} contains non-external labels: {labels}")
    return {"verified": True, "required_outputs": len(required)}


def _load_model_ready() -> dict[str, pd.DataFrame]:
    temperature_only = pd.read_csv(MODEL_READY_DIR / "temperature_only_benchmark.csv")
    multivariate = pd.read_csv(MODEL_READY_DIR / "multivariate_research_reference.csv")
    return {"temperature_only": temperature_only, "multivariate": multivariate}


def _verify_split_contract(data: dict[str, pd.DataFrame]) -> None:
    for name, frame in data.items():
        if set(frame["split"].unique()) != set(SPLIT_ORDER):
            raise ValueError(f"{name} missing expected splits")
        split_runs = {
            split: set(frame.loc[frame["split"] == split, "run_id"])
            for split in SPLIT_ORDER
        }
        overlaps = [
            split_runs[left] & split_runs[right]
            for index, left in enumerate(SPLIT_ORDER)
            for right in SPLIT_ORDER[index + 1 :]
        ]
        if any(overlaps):
            raise ValueError(f"{name} has run_id overlap between splits")


def _evaluate_regression_baselines(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    train = frame.loc[frame["split"] == "train"].copy()
    global_mean = float(train["temperature_dining_c"].mean())
    slot_means = train.groupby("minute_of_day")["temperature_dining_c"].mean()
    for horizon in HORIZONS_MINUTES:
        target = f"target_temperature_{horizon}m"
        for split in SPLIT_ORDER:
            subset = frame.loc[frame["split"] == split].copy()
            expected = subset[target]
            rows.append(
                _regression_row(
                    "temperature_only",
                    f"persistence_{horizon}m",
                    "persistence",
                    horizon,
                    split,
                    expected,
                    subset["temperature_dining_c"],
                )
            )
            historical_mean = (
                subset["minute_of_day"].map(slot_means).fillna(global_mean)
            )
            rows.append(
                _regression_row(
                    "temperature_only",
                    f"historical_mean_{horizon}m",
                    "historical_mean",
                    horizon,
                    split,
                    expected,
                    historical_mean,
                )
            )
            trend = subset["temperature_dining_c"] + subset["temp_trend_4"] * (
                horizon // 15
            )
            rows.append(
                _regression_row(
                    "temperature_only",
                    f"linear_trend_{horizon}m",
                    "linear_trend",
                    horizon,
                    split,
                    expected,
                    trend,
                )
            )
    return rows


def _train_regression_models(
    data: dict[str, pd.DataFrame], model_dir: Path
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    models = {
        "ridge": Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))]),
        "small_tree": DecisionTreeRegressor(max_depth=5, random_state=7),
        "small_forest": RandomForestRegressor(
            n_estimators=60, max_depth=6, min_samples_leaf=4, random_state=7
        ),
    }
    for dataset_name, frame in data.items():
        features = _feature_columns(frame)
        for horizon in HORIZONS_MINUTES:
            target = f"target_temperature_{horizon}m"
            train = frame.loc[frame["split"] == "train"]
            _write_group_validation_report(
                train,
                features,
                target,
                models["ridge"],
                f"{dataset_name}_{horizon}m_regression",
            )
            for model_name, estimator in models.items():
                fitted = clone(estimator)
                fitted.fit(train[features], train[target])
                artifact = model_dir / f"{dataset_name}_{model_name}_{horizon}m.joblib"
                joblib.dump(fitted, artifact)
                for split in SPLIT_ORDER:
                    subset = frame.loc[frame["split"] == split]
                    predicted = fitted.predict(subset[features])
                    rows.append(
                        _regression_row(
                            dataset_name,
                            f"{model_name}_{horizon}m",
                            model_name,
                            horizon,
                            split,
                            subset[target],
                            predicted,
                        )
                    )
    tmp = model_dir / "_tmp.joblib"
    if tmp.exists():
        tmp.unlink()
    return rows


def _train_classification_models(
    data: dict[str, pd.DataFrame], model_dir: Path
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    models = {
        "logistic_regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        max_iter=1000, class_weight="balanced", random_state=7
                    ),
                ),
            ]
        ),
        "small_tree": DecisionTreeClassifier(
            max_depth=5, min_samples_leaf=5, class_weight="balanced", random_state=7
        ),
        "small_forest": RandomForestClassifier(
            n_estimators=60,
            max_depth=6,
            min_samples_leaf=4,
            class_weight="balanced",
            random_state=7,
        ),
    }
    target = "thermal_change_60m"
    for dataset_name, frame in data.items():
        features = _feature_columns(frame)
        train = frame.loc[frame["split"] == "train"]
        _write_group_validation_report(
            train,
            features,
            target,
            models["logistic_regression"],
            f"{dataset_name}_classification",
        )
        for model_name, estimator in models.items():
            fitted = clone(estimator)
            fitted.fit(train[features], train[target])
            artifact = model_dir / f"{dataset_name}_{model_name}_classifier.joblib"
            joblib.dump(fitted, artifact)
            for split in SPLIT_ORDER:
                subset = frame.loc[frame["split"] == split]
                predicted = fitted.predict(subset[features])
                rows.append(
                    {
                        "dataset": dataset_name,
                        "model": model_name,
                        "split": split,
                        "accuracy": float(accuracy_score(subset[target], predicted)),
                        "macro_f1": float(
                            f1_score(subset[target], predicted, average="macro")
                        ),
                        "rows": int(len(subset)),
                    }
                )
    tmp = model_dir / "_tmp.joblib"
    if tmp.exists():
        tmp.unlink()
    return rows


def _feature_columns(frame: pd.DataFrame) -> list[str]:
    excluded = {
        "timestamp",
        "run_id",
        "split",
        "data_source_type",
        "thermal_change_60m",
        "missing_interval_before",
        "sample_index_in_run",
    }
    excluded.update(column for column in frame.columns if column.startswith("target_"))
    return [
        column
        for column in frame.columns
        if column not in excluded
        and pd.api.types.is_numeric_dtype(frame[column])
        and frame[column].notna().all()
    ]


def _regression_row(
    dataset_name: str,
    name: str,
    model: str,
    horizon: int,
    split: str,
    expected: pd.Series,
    predicted: ArrayLike | pd.Series,
) -> dict[str, Any]:
    predicted_series = pd.Series(predicted, index=expected.index)
    rmse = mean_squared_error(expected, predicted_series) ** 0.5
    return {
        "dataset": dataset_name,
        "name": name,
        "model": model,
        "horizon_minutes": horizon,
        "split": split,
        "mae_c": float(mean_absolute_error(expected, predicted_series)),
        "rmse_c": float(rmse),
        "rows": int(len(expected)),
    }


def _write_group_validation_report(
    train: pd.DataFrame,
    features: list[str],
    target: str,
    estimator: BaseEstimator,
    name: str,
) -> None:
    groups = train["run_id"]
    unique_groups = groups.nunique()
    splits = min(5, int(unique_groups))
    rows: list[dict[str, Any]] = []
    if splits < 2:
        return
    cv = GroupKFold(n_splits=splits)
    for fold, (train_idx, validation_idx) in enumerate(
        cv.split(train[features], train[target], groups), start=1
    ):
        fitted = clone(estimator)
        fitted.fit(train.iloc[train_idx][features], train.iloc[train_idx][target])
        predicted = fitted.predict(train.iloc[validation_idx][features])
        if pd.api.types.is_numeric_dtype(train[target]):
            metric = float(
                mean_absolute_error(train.iloc[validation_idx][target], predicted)
            )
            metric_name = "mae_c"
        else:
            metric = float(
                f1_score(train.iloc[validation_idx][target], predicted, average="macro")
            )
            metric_name = "macro_f1"
        rows.append(
            {
                "validation_name": name,
                "fold": fold,
                "metric": metric_name,
                "value": metric,
                "train_run_count": int(train.iloc[train_idx]["run_id"].nunique()),
                "validation_run_count": int(
                    train.iloc[validation_idx]["run_id"].nunique()
                ),
                "zero_run_overlap": bool(
                    set(train.iloc[train_idx]["run_id"]).isdisjoint(
                        set(train.iloc[validation_idx]["run_id"])
                    )
                ),
            }
        )
    report_path = EVIDENCE_DIR / "group_validation_report.csv"
    mode = "a" if report_path.exists() else "w"
    header = not report_path.exists()
    pd.DataFrame(rows).to_csv(report_path, mode=mode, header=header, index=False)


def _write_training_metadata(data: dict[str, pd.DataFrame]) -> None:
    metadata = {
        "dataset_label": DATASET_LABEL,
        "training_only_preprocessing": True,
        "locked_test_split": True,
        "split_run_counts": {
            name: {
                split: int(frame.loc[frame["split"] == split, "run_id"].nunique())
                for split in SPLIT_ORDER
            }
            for name, frame in data.items()
        },
        "model_artifact_dir": str(MODEL_READY_DIR / "models"),
    }
    (MODEL_READY_DIR / "training_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    pd.DataFrame(rows).sort_values(list(rows[0].keys())[:3]).to_csv(path, index=False)


def _plot_metric(frame: pd.DataFrame, metric: str, path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    if "horizon_minutes" in frame.columns:
        suffix = ":" + frame["horizon_minutes"].astype(str) + "m"
    else:
        suffix = ""
    labels = (frame["dataset"] + ":" + frame["model"] + suffix).astype(str)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(labels, frame[metric])
    ax.set_title(title)
    ax.set_ylabel(metric)
    ax.tick_params(axis="x", labelrotation=75)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _write_benchmark_report(
    data: dict[str, pd.DataFrame],
    baseline: pd.DataFrame,
    regression: pd.DataFrame,
    classification: pd.DataFrame,
) -> None:
    test_baseline = baseline.loc[baseline["split"] == "test"]
    test_regression = regression.loc[regression["split"] == "test"]
    test_classification = classification.loc[classification["split"] == "test"]
    lines = [
        "# External T15 Benchmark Report",
        "",
        f"Dataset label: `{DATASET_LABEL}`",
        "",
        "This benchmark is separate from the synthetic cold-chain model pipeline.",
        (
            "The locked test split is evaluated only from the external T15 "
            "model-ready files."
        ),
        "",
        "## Model-Ready Datasets",
        "",
    ]
    for name, frame in data.items():
        lines.append(f"- {name}: {len(frame)} rows")
    lines.extend(["", "## Locked Test Baselines", ""])
    lines.extend(_markdown_table(test_baseline))
    lines.extend(["", "## Locked Test Regression Models", ""])
    lines.extend(_markdown_table(test_regression))
    lines.extend(["", "## Locked Test Classification Models", ""])
    lines.extend(_markdown_table(test_classification))
    lines.extend(
        [
            "",
            "## Plots",
            "",
            "- `plots/test_regression_mae.png`",
            "- `plots/test_classification_macro_f1.png`",
            "",
            "## Limitations",
            "",
            "- External T15 is building-environment data, not cold-chain data.",
            (
                "- Future-temperature targets are derived from later samples in the "
                "same series."
            ),
            (
                "- The multivariate dataset is a research reference and not the "
                "primary deployable benchmark."
            ),
        ]
    )
    (EVIDENCE_DIR / "EXTERNAL_BENCHMARK_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["_No rows._"]
    text = frame.astype(str)
    columns = list(text.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in text.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    return lines


if __name__ == "__main__":
    train_external_models()
    evaluate_external_models()
