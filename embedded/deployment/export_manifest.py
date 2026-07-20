"""Generate embedded deployment manifest for selected model."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import yaml

from ml.inference.model_runtime import ModelRuntime


def create_manifest(
    config_path: Path = Path("config/embedded_export.yaml"),
) -> dict[str, object]:
    """Create and write deployment manifest."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    runtime = ModelRuntime(Path(config["selected_model_path"]))
    if not runtime.loaded or runtime.artifact_dir is None:
        raise RuntimeError(f"Selected model unavailable: {runtime.load_error}")
    pipeline = joblib.load(runtime.artifact_dir / "pipeline.joblib")
    estimator = pipeline.steps[-1][1] if hasattr(pipeline, "steps") else pipeline
    output = Path(config["output_path"])
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "selected_model_name": runtime.model_version,
        "model_version": runtime.model_version,
        "model_type": type(estimator).__name__,
        "source_artifact_paths": {
            "pipeline": str(runtime.artifact_dir / "pipeline.joblib"),
            "preprocessing": str(runtime.artifact_dir / "preprocessing.joblib"),
            "feature_schema": str(runtime.artifact_dir / "feature_schema.json"),
        },
        "checksums": runtime.checksums,
        "feature_count": len(runtime.feature_order),
        "feature_order": runtime.feature_order,
        "feature_units": {
            feature: "derived Celsius/time feature" for feature in runtime.feature_order
        },
        "scaler_type": _scaler_type(pipeline),
        "scaler_parameters": _scaler_parameters(pipeline),
        "class_mapping": runtime.class_mapping,
        "input_numeric_type": config["target_numeric_type"],
        "output_numeric_type": config["target_numeric_type"],
        "probability_representation": "float probability 0.0 to 1.0",
        "required_runtime_operations": _operations(type(estimator).__name__),
        "unsupported_operations": [],
        "estimated_ram_bytes": 0,
        "estimated_flash_bytes": 0,
        "protocol_version": 1,
        "policy_version": "runtime_policy_v1",
        "export_timestamp": datetime.now(UTC).isoformat(),
        "source_git_commit": _git_commit(),
    }
    (output / "deployment_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (output / "deployment_manifest.md").write_text(
        _manifest_markdown(manifest), encoding="utf-8"
    )
    return manifest


def _scaler_type(pipeline: object) -> str:
    if hasattr(pipeline, "named_steps") and "scaler" in pipeline.named_steps:
        return type(pipeline.named_steps["scaler"]).__name__
    return "none"


def _scaler_parameters(pipeline: object) -> dict[str, list[float]]:
    if hasattr(pipeline, "named_steps") and "scaler" in pipeline.named_steps:
        scaler = pipeline.named_steps["scaler"]
        return {
            "mean": np.asarray(getattr(scaler, "mean_", [])).tolist(),
            "scale": np.asarray(getattr(scaler, "scale_", [])).tolist(),
        }
    return {}


def _operations(model_type: str) -> list[str]:
    if model_type == "DecisionTreeClassifier":
        return ["threshold comparison", "branch traversal", "leaf probability lookup"]
    if model_type == "LogisticRegression":
        return ["linear transform", "softmax"]
    if model_type == "MLPClassifier":
        return ["dense layer", "activation", "softmax"]
    return []


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unavailable"


def _manifest_markdown(manifest: dict[str, object]) -> str:
    return "\n".join(
        [
            "# Embedded Deployment Manifest",
            "",
            "PRELIMINARY SOFTWARE EXPORT - NOT STM32 FIRMWARE.",
            "",
            f"Model: `{manifest['selected_model_name']}`",
            f"Type: `{manifest['model_type']}`",
            f"Feature count: {manifest['feature_count']}",
            f"Protocol version: {manifest['protocol_version']}",
            "",
            (
                "Floating-point C export is implemented first; fixed-point "
                "optimization is later work."
            ),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("config/embedded_export.yaml")
    )
    args = parser.parse_args()
    manifest = create_manifest(args.config)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
