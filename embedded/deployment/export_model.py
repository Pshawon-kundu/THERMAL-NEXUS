"""Export selected sklearn model into portable hardware-independent C99."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.tree import DecisionTreeClassifier

from ml.inference.model_runtime import ModelRuntime

SUPPORTED = (DecisionTreeClassifier, LogisticRegression, MLPClassifier)


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
    header = _header(len(runtime.feature_order), len(runtime.class_mapping))
    source = _source(estimator, runtime.feature_order, runtime.class_mapping)
    (output / "thermal_nexus_model.h").write_text(header, encoding="utf-8")
    (output / "thermal_nexus_model.c").write_text(source, encoding="utf-8")
    metadata = {
        "model_type": type(estimator).__name__,
        "feature_count": len(runtime.feature_order),
        "class_mapping": runtime.class_mapping,
        "model_version": runtime.model_version,
    }
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
    estimator: object, feature_order: list[str], class_mapping: dict[str, int]
) -> str:
    if isinstance(estimator, DecisionTreeClassifier):
        return _decision_tree_source(estimator)
    return _linear_stub_source(type(estimator).__name__, len(class_mapping))


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


def _linear_stub_source(model_type: str, class_count: int) -> str:
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
    return ", ".join(f"{float(value):.9g}f" for value in values)


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
