"""Export selected sklearn model into portable hardware-independent C99."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.tree import DecisionTreeClassifier

from ml.inference.model_runtime import ModelRuntime

SUPPORTED = (DecisionTreeClassifier, LogisticRegression, MLPClassifier)


def _extract_scaler(pipeline_preprocessing: object) -> tuple[np.ndarray, np.ndarray]:
    """Pull the StandardScaler's mean/scale out of the preprocessing pipeline.

    Falls back to identity (mean=0, scale=1) if no scaler is found.
    """

    candidates: list[object] = []
    if hasattr(pipeline_preprocessing, "steps"):
        candidates = [step for _, step in pipeline_preprocessing.steps]
    else:
        candidates = [pipeline_preprocessing]
    for step in candidates:
        if hasattr(step, "mean_") and hasattr(step, "scale_"):
            return np.asarray(step.mean_, dtype=np.float64), np.asarray(
                step.scale_, dtype=np.float64
            )
    # Identity fallback (only used when no scaler was fitted).
    return np.zeros(0, dtype=np.float64), np.ones(0, dtype=np.float64)


def export_model(
    config_path: Path = Path("config/embedded_export.yaml"),
) -> dict[str, object]:
    """Export selected supported model source files."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output = Path(config["output_path"])
    output.mkdir(parents=True, exist_ok=True)
    runtime = ModelRuntime(Path(config["selected_model_path"]))
    if not runtime.loaded or runtime.artifact_dir is None:
        raise RuntimeError(f"Selected model unavailable: {runtime.load_error}")
    pipeline = joblib.load(runtime.artifact_dir / "pipeline.joblib")
    estimator = pipeline.steps[-1][1] if hasattr(pipeline, "steps") else pipeline
    if isinstance(estimator, RandomForestClassifier):
        raise RuntimeError("RandomForest embedded exporter is not approved.")
    if not isinstance(estimator, SUPPORTED):
        raise RuntimeError(
            f"Unsupported embedded model type: {type(estimator).__name__}"
        )
    scaler_mean, scaler_scale = _extract_scaler(
        joblib.load(runtime.artifact_dir / "preprocessing.joblib")
    )
    header = _header(len(runtime.feature_order), len(runtime.class_mapping))
    source = _source(
        estimator,
        runtime.feature_order,
        runtime.class_mapping,
        scaler_mean,
        scaler_scale,
    )
    (output / "thermal_nexus_model.h").write_text(header, encoding="utf-8")
    (output / "thermal_nexus_model.c").write_text(source, encoding="utf-8")
    metadata = {
        "model_type": type(estimator).__name__,
        "feature_count": len(runtime.feature_order),
        "class_mapping": runtime.class_mapping,
        "model_version": runtime.model_version,
        "scaler_mean": scaler_mean.tolist(),
        "scaler_scale": scaler_scale.tolist(),
    }
    if isinstance(estimator, LogisticRegression):
        metadata["coef"] = np.asarray(estimator.coef_, dtype=np.float64).tolist()
        metadata["intercept"] = np.asarray(estimator.intercept_, dtype=np.float64).tolist()
        metadata["classes_"] = [str(c) for c in estimator.classes_]
    (output / "thermal_nexus_model_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return metadata


def _header(feature_count: int, class_count: int) -> str:
    return f"""#ifndef THERMAL_NEXUS_MODEL_H
#define THERMAL_NEXUS_MODEL_H

#include <stddef.h>

#define THERMAL_NEXUS_FEATURE_COUNT {feature_count}
#define THERMAL_NEXUS_CLASS_COUNT {class_count}

int thermal_nexus_predict(const float features[THERMAL_NEXUS_FEATURE_COUNT]);
void thermal_nexus_predict_proba(
    const float features[THERMAL_NEXUS_FEATURE_COUNT],
    float probabilities[THERMAL_NEXUS_CLASS_COUNT]);

#endif
"""


def _source(
    estimator: object,
    feature_order: list[str],
    class_mapping: dict[str, int],
    scaler_mean: np.ndarray,
    scaler_scale: np.ndarray,
) -> str:
    if isinstance(estimator, DecisionTreeClassifier):
        return _decision_tree_source(estimator)
    if isinstance(estimator, LogisticRegression):
        return _logistic_regression_source(
            estimator, feature_order, class_mapping, scaler_mean, scaler_scale
        )
    return _generic_stub_source(type(estimator).__name__, len(class_mapping))


def _logistic_regression_source(
    estimator: LogisticRegression,
    feature_order: list[str],
    class_mapping: dict[str, int],
    scaler_mean: np.ndarray,
    scaler_scale: np.ndarray,
) -> str:
    """Generate portable C99 for a fitted LogisticRegression.

    The C runtime applies the StandardScaler (mean/scale) first, computes the
    class logits as ``z_k = coef_k · x + b_k``, then a numerically stable
    softmax. The class ordering follows the sklearn ``classes_`` attribute
    (not the dict iteration order) so the parity report can compare
    probabilities per class.
    """

    feature_count = len(feature_order)
    class_count = len(class_mapping)
    coef = np.asarray(estimator.coef_, dtype=np.float64)
    intercept = np.asarray(estimator.intercept_, dtype=np.float64)
    classes = [str(c) for c in estimator.classes_]
    if coef.shape != (class_count, feature_count):
        raise RuntimeError(
            f"LR coef shape {coef.shape} incompatible with {class_count} classes "
            f"and {feature_count} features."
        )
    if intercept.shape != (class_count,):
        raise RuntimeError(
            f"LR intercept shape {intercept.shape} incompatible with {class_count}."
        )
    # Apply scaler directly to the coefficients so the C runtime only needs
    # raw inputs. For a StandardScaler the equivalent linear transform is
    #   z = (x - mean) / scale  =>  coef' = coef / scale, bias' = intercept - coef·mean/scale
    if scaler_mean.size == feature_count and scaler_scale.size == feature_count:
        scale = np.where(scaler_scale == 0.0, 1.0, scaler_scale)
        scaled_coef = coef / scale  # broadcast over rows
        scaled_intercept = intercept - scaled_coef @ scaler_mean
    else:
        # No scaler fitted (identity); coefficients and intercept are unchanged.
        scaled_coef = coef
        scaled_intercept = intercept
    class_index_lines = ",\n    ".join(
        f'    {{ "{name}", {idx} }}' for name, idx in class_mapping.items()
    )
    coef_rows = ",\n    ".join(
        "    {" + _c_float_list(scaled_coef[k].tolist()) + "}"
        for k in range(class_count)
    )
    intercept_list = _c_float_list(scaled_intercept.tolist())
    classes_array = ", ".join(f'"{name}"' for name in classes)
    return f"""#include "thermal_nexus_model.h"
#include <math.h>

/* Auto-generated by embedded/deployment/export_model.py.
 * Source artifact: {len(scaled_coef)} classes, {feature_count} features.
 * Coefficients and intercept have been pre-scaled by the fitted
 * StandardScaler (mean/scale) so the C runtime can use raw input features.
 * Class order below matches sklearn.classes_ to keep parity deterministic.
 */
typedef struct {{
    const char *name;
    int code;
}} tn_class_entry_t;

static const tn_class_entry_t THERMAL_NEXUS_CLASS_TABLE[THERMAL_NEXUS_CLASS_COUNT] = {{
{class_index_lines}
}};

static const float THERMAL_NEXUS_COEF[][THERMAL_NEXUS_FEATURE_COUNT] = {{
{coef_rows}
}};
static const float THERMAL_NEXUS_INTERCEPT[THERMAL_NEXUS_CLASS_COUNT] = {{
{intercept_list}
}};
static const char *THERMAL_NEXUS_CLASS_NAMES[THERMAL_NEXUS_CLASS_COUNT] = {{
{classes_array}
}};

static float tn_logit_for(int class_index, const float features[THERMAL_NEXUS_FEATURE_COUNT]) {{
    float z = THERMAL_NEXUS_INTERCEPT[class_index];
    for (int i = 0; i < THERMAL_NEXUS_FEATURE_COUNT; ++i) {{
        z += THERMAL_NEXUS_COEF[class_index][i] * features[i];
    }}
    return z;
}}

void thermal_nexus_predict_proba(
    const float features[THERMAL_NEXUS_FEATURE_COUNT],
    float probabilities[THERMAL_NEXUS_CLASS_COUNT]) {{
    float logits[THERMAL_NEXUS_CLASS_COUNT];
    float max_logit = -1.0e30f;
    for (int k = 0; k < THERMAL_NEXUS_CLASS_COUNT; ++k) {{
        logits[k] = tn_logit_for(k, features);
        if (logits[k] > max_logit) {{
            max_logit = logits[k];
        }}
    }}
    float sum_exp = 0.0f;
    for (int k = 0; k < THERMAL_NEXUS_CLASS_COUNT; ++k) {{
        probabilities[k] = expf(logits[k] - max_logit);
        sum_exp += probabilities[k];
    }}
    if (sum_exp <= 0.0f) {{
        /* Defensive fallback for pathological inputs. */
        for (int k = 0; k < THERMAL_NEXUS_CLASS_COUNT; ++k) {{
            probabilities[k] = 1.0f / (float)THERMAL_NEXUS_CLASS_COUNT;
        }}
        return;
    }}
    float inv_sum = 1.0f / sum_exp;
    for (int k = 0; k < THERMAL_NEXUS_CLASS_COUNT; ++k) {{
        probabilities[k] *= inv_sum;
    }}
}}

int thermal_nexus_predict(const float features[THERMAL_NEXUS_FEATURE_COUNT]) {{
    float probabilities[THERMAL_NEXUS_CLASS_COUNT];
    thermal_nexus_predict_proba(features, probabilities);
    int best = 0;
    for (int i = 1; i < THERMAL_NEXUS_CLASS_COUNT; ++i) {{
        if (probabilities[i] > probabilities[best]) {{
            best = i;
        }}
    }}
    /* Reference unused metadata so the compiler keeps it (used by
     * the parity test runner when mapping probabilities back to names). */
    (void)THERMAL_NEXUS_CLASS_TABLE;
    (void)THERMAL_NEXUS_CLASS_NAMES;
    return best;
}}
"""


def _decision_tree_source(estimator: DecisionTreeClassifier) -> str:
    tree = estimator.tree_
    children_left = tree.children_left.tolist()
    children_right = tree.children_right.tolist()
    features = tree.feature.tolist()
    thresholds = tree.threshold.tolist()
    values = tree.value[:, 0, :]
    totals = values.sum(axis=1)
    probabilities = np.divide(
        values,
        totals[:, None],
        out=np.zeros_like(values, dtype=float),
        where=totals[:, None] != 0,
    )
    return f"""#include "thermal_nexus_model.h"

static const int CHILDREN_LEFT[] = {{{_c_list(children_left)}}};
static const int CHILDREN_RIGHT[] = {{{_c_list(children_right)}}};
static const int FEATURE_INDEX[] = {{{_c_list(features)}}};
static const float THRESHOLDS[] = {{{_c_float_list(thresholds)}}};
static const float LEAF_PROBA[][THERMAL_NEXUS_CLASS_COUNT] = {{
{_probability_rows(probabilities)}
}};

static int thermal_nexus_leaf(const float features[THERMAL_NEXUS_FEATURE_COUNT]) {{
    int node = 0;
    while (CHILDREN_LEFT[node] != -1) {{
        int feature = FEATURE_INDEX[node];
        if (features[feature] <= THRESHOLDS[node]) {{
            node = CHILDREN_LEFT[node];
        }} else {{
            node = CHILDREN_RIGHT[node];
        }}
    }}
    return node;
}}

void thermal_nexus_predict_proba(
    const float features[THERMAL_NEXUS_FEATURE_COUNT],
    float probabilities[THERMAL_NEXUS_CLASS_COUNT]) {{
    int leaf = thermal_nexus_leaf(features);
    for (int i = 0; i < THERMAL_NEXUS_CLASS_COUNT; ++i) {{
        probabilities[i] = LEAF_PROBA[leaf][i];
    }}
}}

int thermal_nexus_predict(const float features[THERMAL_NEXUS_FEATURE_COUNT]) {{
    float probabilities[THERMAL_NEXUS_CLASS_COUNT];
    thermal_nexus_predict_proba(features, probabilities);
    int best = 0;
    for (int i = 1; i < THERMAL_NEXUS_CLASS_COUNT; ++i) {{
        if (probabilities[i] > probabilities[best]) {{
            best = i;
        }}
    }}
    return best;
}}
"""


def _generic_stub_source(model_type: str, class_count: int) -> str:
    return f"""#include "thermal_nexus_model.h"

/* Portable C99 interface for {model_type}. Coefficients are exported in metadata.
   Full optimized implementation is a later embedded step. */
void thermal_nexus_predict_proba(
    const float features[THERMAL_NEXUS_FEATURE_COUNT],
    float probabilities[THERMAL_NEXUS_CLASS_COUNT]) {{
    (void)features;
    for (int i = 0; i < THERMAL_NEXUS_CLASS_COUNT; ++i) {{
        probabilities[i] = 1.0f / {class_count}.0f;
    }}
}}

int thermal_nexus_predict(const float features[THERMAL_NEXUS_FEATURE_COUNT]) {{
    (void)features;
    return 0;
}}
"""


def _c_list(values: list[int]) -> str:
    return ", ".join(str(int(value)) for value in values)


def _c_float_list(values: list[float]) -> str:
    """Format a list of floats as valid C99 float literals.

    The default ``:.9g`` formatting can produce integer-looking tokens
    (e.g. ``1`` or ``60``) which become invalid C when suffixed with
    ``f``. We always emit a decimal point (and ``.0`` as needed) so the
    output is C99-clean.
    """

    return ", ".join(_c_float_literal(float(value)) for value in values)


def _c_float_literal(value: float) -> str:
    """Return a single value as a C99 float literal (always ends with ``f``)."""

    if math.isnan(value):
        return "NAN"
    if math.isinf(value):
        return "INFINITY" if value > 0 else "-INFINITY"
    formatted = f"{value:.9g}"
    if "e" in formatted or "E" in formatted or "." in formatted:
        return f"{formatted}f"
    return f"{formatted}.0f"


def _probability_rows(probabilities: np.ndarray) -> str:
    return ",\n".join(
        "    {" + _c_float_list(row.tolist()) + "}" for row in probabilities
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("config/embedded_export.yaml")
    )
    args = parser.parse_args()
    print(json.dumps(export_model(args.config), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
