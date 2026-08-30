"""Temperature-Only V1 baselines, candidate training, and evaluation."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeRegressor

from ml.temp_v1.pipeline import FEATURE_COLUMNS, HORIZONS

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache")))

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DATA_DIR = Path("ml/data/temp_v1")
SPLIT_DIR = DATA_DIR / "splits"
MODEL_DIR = Path("ml/models/temp_v1")
CANDIDATE_DIR = MODEL_DIR / "candidates"
SELECTED_DIR = MODEL_DIR / "selected"
EVIDENCE_DIR = Path("evidence/temp_v1")
PLOTS_DIR = EVIDENCE_DIR / "plots"
STATUS = "DEVELOPMENT_ONLY"


def load_split(name: str) -> pd.DataFrame:
    return pd.read_csv(SPLIT_DIR / f"{name}.csv")


def persistence_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    """Predict the current temperature at every requested horizon."""
    return pd.DataFrame(
        {f"target_temp_{horizon}m_c": frame["inside_temp_c"] for horizon in HORIZONS},
        index=frame.index,
    )


def trend_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    """Extrapolate the historical 15-minute slope without future information."""
    slope = frame["temp_slope_15m"]
    return pd.DataFrame(
        {
            f"target_temp_{horizon}m_c": frame["inside_temp_c"] + slope * horizon
            for horizon in HORIZONS
        },
        index=frame.index,
    )


def metrics_by_horizon(
    actual: pd.DataFrame, predicted: pd.DataFrame
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for horizon in HORIZONS:
        target = f"target_temp_{horizon}m_c"
        metrics[f"mae_{horizon}m"] = float(
            mean_absolute_error(actual[target], predicted[target])
        )
        metrics[f"rmse_{horizon}m"] = float(
            mean_squared_error(actual[target], predicted[target]) ** 0.5
        )
    metrics["mean_mae"] = float(np.mean([metrics[f"mae_{h}m"] for h in HORIZONS]))
    metrics["mean_rmse"] = float(np.mean([metrics[f"rmse_{h}m"] for h in HORIZONS]))
    return metrics


def dynamics_labels(frame: pd.DataFrame) -> pd.Series:
    delta = frame["temp_delta_5m"]
    return pd.Series(
        np.select(
            [delta > 0.05, delta < -0.05],
            ["WARMING", "COOLING"],
            default="STABLE",
        ),
        index=frame.index,
    )


def dynamics_metrics(
    actual: pd.DataFrame, predicted: pd.DataFrame, name: str
) -> pd.DataFrame:
    labels = dynamics_labels(actual)
    rows = []
    for state in ("STABLE", "WARMING", "COOLING"):
        selected = labels == state
        for horizon in HORIZONS:
            target = f"target_temp_{horizon}m_c"
            rows.append(
                {
                    "system": name,
                    "state": state,
                    "horizon_minutes": horizon,
                    "rows": int(selected.sum()),
                    "mae_c": float(
                        mean_absolute_error(
                            actual.loc[selected, target],
                            predicted.loc[selected, target],
                        )
                    )
                    if selected.any()
                    else None,
                }
            )
    return pd.DataFrame(rows)


def temperature_bin_metrics(
    actual: pd.DataFrame, predicted: pd.DataFrame, name: str
) -> pd.DataFrame:
    bins = [16, 18, 20, 22, 24, 26, 28, 30]
    labels = [
        f"{left}-{right}" for left, right in zip(bins[:-1], bins[1:], strict=True)
    ]
    categories = pd.cut(actual["inside_temp_c"], bins=bins, right=False, labels=labels)
    rows = []
    for label in labels:
        selected = categories == label
        for horizon in HORIZONS:
            target = f"target_temp_{horizon}m_c"
            rows.append(
                {
                    "system": name,
                    "temperature_bin_c": label,
                    "horizon_minutes": horizon,
                    "rows": int(selected.sum()),
                    "sparse": bool(selected.sum() < 20),
                    "mae_c": float(
                        mean_absolute_error(
                            actual.loc[selected, target],
                            predicted.loc[selected, target],
                        )
                    )
                    if selected.any()
                    else None,
                }
            )
    return pd.DataFrame(rows)


def source_metrics(
    actual: pd.DataFrame, predicted: pd.DataFrame, name: str
) -> pd.DataFrame:
    rows = []
    for source, source_frame in actual.groupby("source_dataset", sort=True):
        source_prediction = predicted.loc[source_frame.index]
        rows.append(
            {
                "system": name,
                "source_dataset": source,
                "rows": int(len(source_frame)),
                **metrics_by_horizon(source_frame, source_prediction),
            }
        )
    return pd.DataFrame(rows)


def _estimator(name: str) -> Pipeline:
    if name == "ridge":
        return Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))])
    if name == "decision_tree":
        return Pipeline(
            [
                (
                    "model",
                    DecisionTreeRegressor(
                        max_depth=8, min_samples_leaf=4, random_state=42
                    ),
                )
            ]
        )
    if name == "random_forest":
        return Pipeline(
            [
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=100,
                        max_depth=12,
                        min_samples_leaf=2,
                        random_state=42,
                        n_jobs=-1,
                    ),
                )
            ]
        )
    raise ValueError(f"Unknown model: {name}")


def _predict_models(
    models: dict[str, dict[int, Pipeline]], frame: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    outputs = {}
    features = frame[list(FEATURE_COLUMNS)]
    for name, horizon_models in models.items():
        outputs[name] = pd.DataFrame(
            {
                f"target_temp_{horizon}m_c": horizon_models[horizon].predict(features)
                for horizon in HORIZONS
            },
            index=frame.index,
        )
    return outputs


def _model_complexity(model: Pipeline) -> dict[str, Any]:
    estimator = model[-1]
    if isinstance(estimator, DecisionTreeRegressor):
        return {
            "tree_depth": int(estimator.get_depth()),
            "leaf_count": int(estimator.get_n_leaves()),
            "node_count": int(estimator.tree_.node_count),
            "tree_count": 1,
        }
    if isinstance(estimator, RandomForestRegressor):
        return {
            "tree_depth": int(max(tree.get_depth() for tree in estimator.estimators_)),
            "leaf_count": int(
                sum(tree.get_n_leaves() for tree in estimator.estimators_)
            ),
            "node_count": int(
                sum(tree.tree_.node_count for tree in estimator.estimators_)
            ),
            "tree_count": int(len(estimator.estimators_)),
        }
    return {
        "tree_depth": None,
        "leaf_count": None,
        "node_count": None,
        "tree_count": None,
    }


def _fit_candidates(
    train: pd.DataFrame,
) -> tuple[dict[str, dict[int, Pipeline]], pd.DataFrame]:
    models: dict[str, dict[int, Pipeline]] = {}
    rows = []
    features = train[list(FEATURE_COLUMNS)]
    for name in ("ridge", "decision_tree", "random_forest"):
        models[name] = {}
        for horizon in HORIZONS:
            model = _estimator(name)
            target = f"target_temp_{horizon}m_c"
            started = time.perf_counter()
            model.fit(features, train[target])
            training_seconds = time.perf_counter() - started
            model_path = CANDIDATE_DIR / name / f"{horizon}m.joblib"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, model_path)
            started = time.perf_counter()
            for _ in range(20):
                model.predict(features.iloc[:1])
            latency_ms = (time.perf_counter() - started) * 1000 / 20
            rows.append(
                {
                    "model": name,
                    "horizon_minutes": horizon,
                    "training_seconds": training_seconds,
                    "inference_latency_ms": latency_ms,
                    "model_size_bytes": model_path.stat().st_size,
                    "feature_count": len(FEATURE_COLUMNS),
                    **_model_complexity(model),
                }
            )
            models[name][horizon] = model
    return models, pd.DataFrame(rows)


def _select_model(comparison: pd.DataFrame) -> tuple[str, dict[str, Any]]:
    grouped = comparison.groupby("model", as_index=False).agg(
        mean_mae=("mean_mae", "first"),
        mean_rmse=("mean_rmse", "first"),
        dynamic_mae=("dynamic_mae", "first"),
        model_size_bytes=("model_size_bytes", "sum"),
    )
    best_mae = grouped["mean_mae"].min()
    eligible = grouped[grouped["mean_mae"] <= best_mae * 1.05]
    selected = eligible.sort_values(
        ["model_size_bytes", "dynamic_mae", "mean_rmse", "model"],
        ascending=[True, True, True, True],
    ).iloc[0]
    rationale = {
        "selected_model": str(selected["model"]),
        "rule": (
            "Keep validation mean MAE within 5% of the best, then prefer smaller "
            "model, lower warming/cooling MAE, lower RMSE, and deterministic "
            "name order."
        ),
        "test_used_for_selection": False,
        "validation_only": True,
        "eligible_models": eligible["model"].tolist(),
    }
    return str(selected["model"]), rationale


def _write_plots(
    actual: pd.DataFrame, predicted: pd.DataFrame, labels: pd.Series
) -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    for horizon in HORIZONS:
        target = f"target_temp_{horizon}m_c"
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.scatter(actual[target], predicted[target], s=8, alpha=0.45)
        ax.set_xlabel("Actual temperature C")
        ax.set_ylabel("Predicted temperature C")
        ax.set_title(f"Temperature-only V1 actual vs predicted +{horizon}m")
        fig.tight_layout()
        fig.savefig(PLOTS_DIR / f"actual_vs_predicted_{horizon}m.png", dpi=150)
        plt.close(fig)
    errors = pd.concat(
        [
            predicted[f"target_temp_{h}m_c"] - actual[f"target_temp_{h}m_c"]
            for h in HORIZONS
        ],
        ignore_index=True,
    )
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(errors, bins=30)
    ax.set_xlabel("Prediction error C")
    ax.set_ylabel("Count")
    ax.set_title("Temperature-only V1 prediction error")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "prediction_error_distribution.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(actual["inside_temp_c"], errors.iloc[: len(actual)], s=8, alpha=0.45)
    ax.set_xlabel("Actual current temperature C")
    ax.set_ylabel("+5m prediction error C")
    ax.set_title("Prediction error versus actual temperature")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "error_vs_actual_temperature.png", dpi=150)
    plt.close(fig)
    dynamics = labels.value_counts().reindex(["STABLE", "WARMING", "COOLING"])
    fig, ax = plt.subplots(figsize=(6, 4))
    dynamics.plot(kind="bar", ax=ax)
    ax.set_ylabel("Count")
    ax.set_title("Held-out thermal dynamics")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "dynamics_comparison.png", dpi=150)
    plt.close(fig)


def _source_holdouts(all_frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for source in ("UCI_ROOM_OCCUPANCY", "INTEL_LAB", "BOLZANO_IEQ"):
        train = all_frame[all_frame["source_dataset"] != source]
        holdout = all_frame[all_frame["source_dataset"] == source]
        if train.empty or holdout.empty:
            continue
        for name in ("ridge", "decision_tree", "random_forest"):
            models = {
                horizon: _estimator(name).fit(
                    train[list(FEATURE_COLUMNS)], train[f"target_temp_{horizon}m_c"]
                )
                for horizon in HORIZONS
            }
            predicted = pd.DataFrame(
                {
                    f"target_temp_{horizon}m_c": models[horizon].predict(
                        holdout[list(FEATURE_COLUMNS)]
                    )
                    for horizon in HORIZONS
                },
                index=holdout.index,
            )
            metrics = metrics_by_horizon(holdout, predicted)
            rows.append({"held_out_source": source, "model": name, **metrics})
    return pd.DataFrame(rows)


def train_and_evaluate() -> dict[str, Any]:
    """Run the frozen-split development experiment and lock the test result."""
    train = load_split("train")
    validation = load_split("validation")
    test = load_split("test")
    all_frame = pd.concat([train, validation, test], ignore_index=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    persistence_val = persistence_predictions(validation)
    trend_val = trend_predictions(validation)
    baseline_rows = []
    for name, prediction in (
        ("persistence", persistence_val),
        ("linear_trend", trend_val),
    ):
        baseline_rows.append(
            {"system": name, **metrics_by_horizon(validation, prediction)}
        )
    pd.DataFrame(baseline_rows).to_csv(
        EVIDENCE_DIR / "baseline_comparison.csv", index=False
    )
    models, profile = _fit_candidates(train)
    candidate_outputs = _predict_models(models, validation)
    comparison_rows = []
    dynamics_frames = [
        dynamics_metrics(validation, persistence_val, "persistence"),
        dynamics_metrics(validation, trend_val, "linear_trend"),
    ]
    bin_frames = []
    for name, output in candidate_outputs.items():
        metric = metrics_by_horizon(validation, output)
        dynamics = dynamics_metrics(validation, output, name)
        bins = temperature_bin_metrics(validation, output, name)
        dynamics_frames.append(dynamics)
        bin_frames.append(bins)
        dynamic_mae = float(
            dynamics[dynamics["state"].isin(["WARMING", "COOLING"])]["mae_c"].mean()
        )
        comparison_rows.append({"model": name, **metric, "dynamic_mae": dynamic_mae})
    comparison = pd.DataFrame(comparison_rows).merge(
        profile.groupby("model", as_index=False).agg(
            {
                "model_size_bytes": "sum",
                "training_seconds": "sum",
                "inference_latency_ms": "mean",
                "feature_count": "first",
                "tree_depth": "max",
                "leaf_count": "sum",
                "node_count": "sum",
                "tree_count": "sum",
            }
        ),
        on="model",
    )
    selected_name, selection = _select_model(comparison)
    comparison.to_csv(EVIDENCE_DIR / "model_comparison.csv", index=False)
    pd.concat(dynamics_frames, ignore_index=True).to_csv(
        EVIDENCE_DIR / "dynamics_metrics.csv", index=False
    )
    pd.concat(bin_frames, ignore_index=True).to_csv(
        EVIDENCE_DIR / "temperature_bin_metrics.csv", index=False
    )
    holdouts = _source_holdouts(all_frame)
    holdouts.to_csv(EVIDENCE_DIR / "source_holdout_metrics.csv", index=False)
    validation_source_frames = [
        source_metrics(validation, output, name)
        for name, output in candidate_outputs.items()
    ]
    pd.concat(validation_source_frames, ignore_index=True).to_csv(
        EVIDENCE_DIR / "source_metrics.csv", index=False
    )
    selected_models = models[selected_name]
    selected_dir = SELECTED_DIR
    selected_dir.mkdir(parents=True, exist_ok=True)
    for horizon, model in selected_models.items():
        joblib.dump(model, selected_dir / f"model_{horizon}m.joblib")
    joblib.dump(selected_models[5], selected_dir / "model.joblib")
    selected_model_path = selected_dir / "model_5m.joblib"
    reload_model = joblib.load(selected_model_path)
    reload_check = np.allclose(
        selected_models[5].predict(validation[list(FEATURE_COLUMNS)].iloc[:50]),
        reload_model.predict(validation[list(FEATURE_COLUMNS)].iloc[:50]),
    )
    selected_outputs = _predict_models({selected_name: selected_models}, test)[
        selected_name
    ]
    test_metrics = metrics_by_horizon(test, selected_outputs)
    test_metrics["TEST_SET_USED"] = True
    test_metrics["status"] = STATUS
    test_baseline_metrics = metrics_by_horizon(test, persistence_predictions(test))
    test_metrics["improvement_over_persistence_mean_mae_c"] = float(
        test_baseline_metrics["mean_mae"] - test_metrics["mean_mae"]
    )
    (selected_dir / "test_metrics.json").write_text(
        json.dumps(test_metrics, indent=2), encoding="utf-8"
    )
    validation_metrics = (
        comparison[comparison["model"] == selected_name].iloc[0].to_dict()
    )
    (selected_dir / "validation_metrics.json").write_text(
        json.dumps(validation_metrics, indent=2, default=str), encoding="utf-8"
    )
    (selected_dir / "selection.json").write_text(
        json.dumps(selection, indent=2), encoding="utf-8"
    )
    (selected_dir / "feature_schema.json").write_text(
        json.dumps(
            {
                "features": list(FEATURE_COLUMNS),
                "targets": [f"target_temp_{h}m_c" for h in HORIZONS],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (selected_dir / "model_metadata.json").write_text(
        json.dumps(
            {
                "status": STATUS,
                "architecture": "one model per horizon",
                "selected_model": selected_name,
                "test_set_used": True,
                "reload_predictions_match": bool(reload_check),
                "test_selection_used": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    joblib.dump(
        selected_models[5].named_steps.get("scaler", "passthrough"),
        selected_dir / "preprocessing.joblib",
    )
    (selected_dir / "MODEL_CARD.md").write_text(
        f"# Temperature-Only V1 Development Model\n\n"
        f"Selected model: `{selected_name}`\n\n"
        f"Status: `{STATUS}`. This model is not cold-chain, biological, vaccine, "
        "organ, or full 16-32 C validation.\n",
        encoding="utf-8",
    )
    _write_plots(test, selected_outputs, dynamics_labels(test))
    pd.concat(
        [
            pd.read_csv(EVIDENCE_DIR / "dynamics_metrics.csv"),
            dynamics_metrics(test, selected_outputs, f"{selected_name}_test"),
        ],
        ignore_index=True,
    ).to_csv(EVIDENCE_DIR / "dynamics_metrics.csv", index=False)
    pd.concat(
        [
            pd.read_csv(EVIDENCE_DIR / "temperature_bin_metrics.csv"),
            temperature_bin_metrics(test, selected_outputs, f"{selected_name}_test"),
        ],
        ignore_index=True,
    ).to_csv(EVIDENCE_DIR / "temperature_bin_metrics.csv", index=False)
    pd.concat(
        [
            pd.read_csv(EVIDENCE_DIR / "source_metrics.csv"),
            source_metrics(test, selected_outputs, f"{selected_name}_test"),
        ],
        ignore_index=True,
    ).to_csv(EVIDENCE_DIR / "source_metrics.csv", index=False)
    final_report = {
        "selected_model": selected_name,
        "selection": selection,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "reload_check": bool(reload_check),
        "status": STATUS,
        "test_set_used": True,
    }
    (EVIDENCE_DIR / "test_report.json").write_text(
        json.dumps(final_report, indent=2, default=str), encoding="utf-8"
    )
    return final_report


def verify() -> int:
    required = [SELECTED_DIR / f"model_{horizon}m.joblib" for horizon in HORIZONS]
    required.append(SELECTED_DIR / "model.joblib")
    required += [
        SELECTED_DIR / name
        for name in (
            "preprocessing.joblib",
            "feature_schema.json",
            "model_metadata.json",
            "validation_metrics.json",
            "test_metrics.json",
            "selection.json",
            "MODEL_CARD.md",
        )
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing Temperature-Only V1 artifacts: " + ", ".join(missing)
        )
    print("Temperature-Only V1 model artifacts verified.")
    return 0


def evaluate() -> dict[str, Any]:
    verify()
    return json.loads((EVIDENCE_DIR / "test_report.json").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("train", "evaluate", "verify"))
    args = parser.parse_args()
    if args.command == "train":
        print(json.dumps(train_and_evaluate(), indent=2, default=str))
    elif args.command == "evaluate":
        print(json.dumps(evaluate(), indent=2, default=str))
    else:
        return verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
