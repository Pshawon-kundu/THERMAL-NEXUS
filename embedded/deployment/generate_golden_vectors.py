"""Generate Python golden vectors for embedded parity checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from embedded.deployment.export_model import _c_float_list
from ml.inference.model_runtime import ModelRuntime
from simulator.sensor_node.config import load_runtime_policy
from simulator.sensor_node.policy import policy_for_state


def generate_golden_vectors(
    config_path: Path = Path("config/embedded_export.yaml"),
    source_csv: Path = Path("ml/data/splits/validation.csv"),
) -> list[dict[str, Any]]:
    """Generate deterministic representative validation vectors."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    count = int(config["golden_vector_count_per_class"])
    runtime = ModelRuntime(Path(config["selected_model_path"]))
    if not runtime.loaded:
        raise RuntimeError(f"Selected model unavailable: {runtime.load_error}")
    frame = pd.read_csv(source_csv)
    vectors: list[dict[str, Any]] = []
    for state, group in frame.groupby("thermal_state", sort=True):
        for _, row in group.head(count).iterrows():
            vectors.append(_vector(row, state, runtime))
    near = frame.sort_values("distance_from_nearest_limit").head(count)
    for _, row in near.iterrows():
        vectors.append(_vector(row, "near_threshold", runtime))
    output = Path("embedded/golden_vectors")
    output.mkdir(parents=True, exist_ok=True)
    (output / "golden_vectors.json").write_text(
        json.dumps(vectors, indent=2), encoding="utf-8"
    )
    pd.DataFrame(vectors).to_csv(output / "golden_vectors.csv", index=False)
    (output / "golden_vectors.h").write_text(
        _header(vectors, runtime), encoding="utf-8"
    )
    return vectors


def _vector(row: pd.Series, label: str, runtime: ModelRuntime) -> dict[str, Any]:
    features = {name: float(row[name]) for name in runtime.feature_order}
    prediction = runtime.predict(pd.DataFrame([features]))
    policy = load_runtime_policy(Path("config/runtime_policy.yaml"))
    applied_policy = policy_for_state(
        (
            prediction.predicted_state
            if prediction.predicted_state != "MODEL_FAULT"
            else "MODEL_FAULT"
        ),
        policy,
    )
    return {
        "vector_id": f"{label}_{len(str(row['run_id']))}_{int(row.name)}",
        "source_run_id": row["run_id"],
        "timestamp": row["timestamp"],
        "raw_feature_values": features,
        "preprocessed_feature_values": features,
        "python_predicted_class": prediction.predicted_state,
        "python_class_probabilities": prediction.probabilities,
        "expected_policy_state": prediction.predicted_state,
        "expected_sampling_interval": applied_policy.sampling_interval_seconds,
        "expected_transmission_interval": applied_policy.transmission_interval_seconds,
        "model_version": prediction.model_version,
        "feature_schema_checksum": runtime.checksums.get("feature_schema.json", ""),
    }


def _header(vectors: list[dict[str, Any]], runtime: ModelRuntime) -> str:
    rows = []
    for vector in vectors:
        values = vector["raw_feature_values"]
        rows.append(
            "    {"
            + _c_float_list([float(values[name]) for name in runtime.feature_order])
            + "}"
        )
    joined_rows = ",\n".join(rows)
    return f"""#ifndef THERMAL_NEXUS_GOLDEN_VECTORS_H
#define THERMAL_NEXUS_GOLDEN_VECTORS_H
#include "../generated/thermal_nexus_model.h"
#define THERMAL_NEXUS_GOLDEN_VECTOR_COUNT {len(vectors)}
static const float THERMAL_NEXUS_GOLDEN_FEATURES[][THERMAL_NEXUS_FEATURE_COUNT] = {{
{joined_rows}
}};
#endif
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("config/embedded_export.yaml")
    )
    parser.add_argument(
        "--source", type=Path, default=Path("ml/data/splits/validation.csv")
    )
    args = parser.parse_args()
    vectors = generate_golden_vectors(args.config, args.source)
    print(json.dumps({"vectors": len(vectors)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
