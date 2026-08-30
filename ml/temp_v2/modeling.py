"""V2 delta-regression candidates, weighted comparison, and acceptance gate."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet, HuberRegressor, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeRegressor

from ml.temp_v2.paths import EVIDENCE_DIR, MODEL_DIR
from ml.temp_v2.pipeline import (
    FEATURE_COLUMNS,
    HORIZONS,
    prepare_v2_data,
    reconstruct_temperature,
)

TARGETS = [f"delta_temp_{horizon}m_c" for horizon in HORIZONS]
STATUS = "DEVELOPMENT_ONLY"


def _model(name: str) -> Pipeline:
    if name == "ridge":
        estimator = Ridge(alpha=1.0)
    elif name == "huber":
        estimator = HuberRegressor(epsilon=1.35, alpha=0.0001, max_iter=500)
    elif name == "elastic_net":
        estimator = ElasticNet(
            alpha=0.001, l1_ratio=0.2, max_iter=5000, random_state=42
        )
    elif name == "decision_tree":
        estimator = DecisionTreeRegressor(
            max_depth=5, min_samples_leaf=8, random_state=42
        )
    else:
        raise ValueError(name)
    return (
        Pipeline([("scaler", StandardScaler()), ("model", estimator)])
        if name != "decision_tree"
        else Pipeline([("model", estimator)])
    )


def labels(frame: pd.DataFrame, horizon: int = 5) -> pd.Series:
    delta = frame[f"delta_temp_{horizon}m_c"]
    return pd.Series(
        np.select(
            [delta > 0.05, delta < -0.05], ["WARMING", "COOLING"], default="STABLE"
        ),
        index=frame.index,
    )


def metrics(
    actual: pd.DataFrame, predicted: pd.DataFrame, prefix: str = ""
) -> dict[str, float]:
    output = {}
    for horizon in HORIZONS:
        target = f"target_temp_{horizon}m_c"
        output[f"mae_{horizon}m"] = float(
            mean_absolute_error(actual[target], predicted[target])
        )
        output[f"rmse_{horizon}m"] = float(
            mean_squared_error(actual[target], predicted[target]) ** 0.5
        )
    output["mean_mae"] = float(np.mean([output[f"mae_{h}m"] for h in HORIZONS]))
    output["mean_rmse"] = float(np.mean([output[f"rmse_{h}m"] for h in HORIZONS]))
    return {f"{prefix}{key}": value for key, value in output.items()}


def direction_metrics(
    actual: pd.DataFrame, predicted: pd.DataFrame, horizon: int
) -> dict[str, float]:
    actual_label = labels(actual, horizon)
    predicted_delta = predicted[f"target_temp_{horizon}m_c"] - actual["inside_temp_c"]
    predicted_label = pd.Series(
        np.select(
            [predicted_delta > 0.05, predicted_delta < -0.05],
            ["WARMING", "COOLING"],
            default="STABLE",
        ),
        index=actual.index,
    )
    matrix = pd.crosstab(actual_label, predicted_label).reindex(
        index=["STABLE", "WARMING", "COOLING"],
        columns=["STABLE", "WARMING", "COOLING"],
        fill_value=0,
    )
    return {
        "horizon_minutes": horizon,
        "direction_accuracy": float((actual_label == predicted_label).mean()),
        "warming_recall": float(
            matrix.loc["WARMING", "WARMING"] / matrix.loc["WARMING"].sum()
        )
        if "WARMING" in matrix.index
        else 0.0,
        "cooling_recall": float(
            matrix.loc["COOLING", "COOLING"] / matrix.loc["COOLING"].sum()
        )
        if "COOLING" in matrix.index
        else 0.0,
    }


def _weights(frame: pd.DataFrame) -> np.ndarray:
    state = labels(frame, 5)
    return state.map({"STABLE": 1.0, "WARMING": 2.0, "COOLING": 2.0}).to_numpy()


def _dynamic_rows(
    actual: pd.DataFrame, predicted: pd.DataFrame, system: str
) -> pd.DataFrame:
    rows = []
    for state in ("STABLE", "WARMING", "COOLING"):
        selected = labels(actual, 5) == state
        for horizon in HORIZONS:
            target = f"target_temp_{horizon}m_c"
            rows.append(
                {
                    "system": system,
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


def _fit_predict(
    train: pd.DataFrame, validation: pd.DataFrame, name: str, weighted: bool
) -> tuple[dict[int, Pipeline], pd.DataFrame, dict[str, Any]]:
    models = {}
    profile = {
        "model": name,
        "weighted": weighted,
        "training_seconds": 0.0,
        "model_size_bytes": 0,
        "feature_count": len(FEATURE_COLUMNS),
    }
    for horizon in HORIZONS:
        estimator = _model(name)
        start = time.perf_counter()
        fit_kwargs = {"model__sample_weight": _weights(train)} if weighted else {}
        estimator.fit(
            train[list(FEATURE_COLUMNS)],
            train[f"delta_temp_{horizon}m_c"],
            **fit_kwargs,
        )
        profile["training_seconds"] += time.perf_counter() - start
        models[horizon] = estimator
        candidate_path = (
            MODEL_DIR
            / "candidates"
            / name
            / f"{'weighted' if weighted else 'unweighted'}_{horizon}m.joblib"
        )
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(estimator, candidate_path)
        profile["model_size_bytes"] += candidate_path.stat().st_size
    predictions = pd.DataFrame(
        {
            f"target_temp_{horizon}m_c": validation["inside_temp_c"]
            + models[horizon].predict(validation[list(FEATURE_COLUMNS)])
            for horizon in HORIZONS
        },
        index=validation.index,
    )
    profile.update(metrics(validation, predictions))
    profile["dynamic_mae"] = float(
        np.mean(
            [
                metrics(
                    validation[labels(validation, 5) != "STABLE"],
                    predictions.loc[labels(validation, 5) != "STABLE"],
                )[f"mae_{h}m"]
                for h in HORIZONS
            ]
        )
    )
    return models, predictions, profile


def run_v2() -> dict[str, Any]:
    prepare_v2_data()
    train = pd.read_csv(Path("ml/data/temp_v2/train.csv"))
    validation = pd.read_csv(Path("ml/data/temp_v2/validation.csv"))
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    persistence = reconstruct_temperature(
        validation,
        pd.DataFrame({target: 0.0 for target in TARGETS}, index=validation.index),
    )
    baseline = metrics(validation, persistence)
    _dynamic_rows(validation, persistence, "persistence").to_csv(
        EVIDENCE_DIR / "dynamics_metrics.csv", index=False
    )
    pd.DataFrame(
        [direction_metrics(validation, persistence, horizon) for horizon in HORIZONS]
    ).to_csv(EVIDENCE_DIR / "direction_metrics.csv", index=False)
    candidates = []
    fitted = {}
    for name in ("ridge", "huber", "elastic_net", "decision_tree"):
        for weighted in (False, True):
            models, prediction, profile = _fit_predict(
                train, validation, name, weighted
            )
            profile["weighted"] = weighted
            candidates.append(profile)
            fitted[(name, weighted)] = (models, prediction)
    direction_rows = []
    for (name, weighted), (_, prediction) in fitted.items():
        direction_rows.extend(
            {
                "system": f"{name}_{'weighted' if weighted else 'unweighted'}",
                **direction_metrics(validation, prediction, horizon),
            }
            for horizon in HORIZONS
        )
    pd.DataFrame(direction_rows).to_csv(
        EVIDENCE_DIR / "direction_metrics.csv", index=False
    )
    comparison = pd.DataFrame(candidates)
    comparison["improvement_mean_mae_c"] = baseline["mean_mae"] - comparison["mean_mae"]
    comparison["improvement_mean_mae_percent"] = (
        comparison["improvement_mean_mae_c"] / baseline["mean_mae"] * 100.0
    )
    comparison.to_csv(EVIDENCE_DIR / "model_comparison.csv", index=False)
    pd.DataFrame([{"system": "persistence_delta_zero", **baseline}]).to_csv(
        EVIDENCE_DIR / "baseline_comparison.csv", index=False
    )
    best_baseline = baseline["mean_mae"]
    eligible = comparison[
        (comparison["mean_mae"] < best_baseline)
        & (comparison["dynamic_mae"] <= comparison["mean_mae"] * 2.0)
    ]
    gate_passed = not eligible.empty
    selected_row = (
        eligible.sort_values(
            ["mean_mae", "model_size_bytes", "model", "weighted"]
        ).iloc[0]
        if gate_passed
        else None
    )
    selected = str(selected_row["model"]) if gate_passed else None
    weighted = bool(selected_row["weighted"]) if gate_passed else False
    selection = {
        "status": "DEVELOPMENT_ML_CANDIDATE"
        if gate_passed
        else "ML_CANDIDATE_REJECTED_BASELINE_BETTER",
        "selected_model": selected,
        "weighted": weighted,
        "baseline_mean_mae": best_baseline,
        "eligible_models": eligible[["model", "weighted"]].to_dict(orient="records"),
        "test_used_for_selection": False,
    }
    (MODEL_DIR / "selection.json").write_text(
        json.dumps(selection, indent=2), encoding="utf-8"
    )
    if gate_passed:
        models, prediction = fitted[(selected, weighted)]
        selected_dir = MODEL_DIR / "selected"
        selected_dir.mkdir(parents=True, exist_ok=True)
        for horizon, model in models.items():
            joblib.dump(model, selected_dir / f"model_{horizon}m.joblib")
        joblib.dump(models[5], selected_dir / "model.joblib")
        (selected_dir / "preprocessing.joblib").write_bytes(
            b"V2 preprocessing is embedded in each pipeline artifact"
        )
        (selected_dir / "feature_schema.json").write_text(
            json.dumps(
                {"features": list(FEATURE_COLUMNS), "targets": TARGETS}, indent=2
            ),
            encoding="utf-8",
        )
        (selected_dir / "model_metadata.json").write_text(
            json.dumps(
                {
                    "version": "TEMP_V2",
                    "status": selection["status"],
                    "target_formulation": "delta temperature",
                    "real_test_available": False,
                    "v1_test_reused_for_final": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    (EVIDENCE_DIR / "acceptance_gate.json").write_text(
        json.dumps(selection, indent=2), encoding="utf-8"
    )
    return {
        "baseline": baseline,
        "selection": selection,
        "candidate_count": len(comparison),
    }


if __name__ == "__main__":
    print(json.dumps(run_v2(), indent=2))
