"""Estimate embedded resource use from generated artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import yaml

from ml.inference.model_runtime import ModelRuntime


def estimate_resources(
    config_path: Path = Path("config/embedded_export.yaml"),
    evidence_dir: Path = Path("evidence/embedded"),
) -> dict[str, object]:
    """Create software-only resource estimates."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    runtime = ModelRuntime(Path(config["selected_model_path"]))
    if not runtime.loaded or runtime.artifact_dir is None:
        raise RuntimeError(f"Selected model unavailable: {runtime.load_error}")
    pipeline = joblib.load(runtime.artifact_dir / "pipeline.joblib")
    estimator = pipeline.steps[-1][1] if hasattr(pipeline, "steps") else pipeline
    float_bytes = int(config["resource_estimate_assumptions"]["float_bytes"])
    feature_count = len(runtime.feature_order)
    if hasattr(estimator, "tree_"):
        parameter_count = int(
            estimator.tree_.node_count * (4 + len(runtime.class_mapping))
        )
        operations = int(estimator.tree_.max_depth)
    else:
        parameter_count = feature_count * len(runtime.class_mapping)
        operations = parameter_count
    generated = Path(config["output_path"])
    source_size = sum(
        path.stat().st_size for path in generated.glob("*") if path.is_file()
    )
    estimate = {
        "value_type": "ESTIMATED_SOFTWARE_VALUE",
        "model_parameter_count": parameter_count,
        "model_constant_bytes": parameter_count * float_bytes,
        "preprocessing_constant_bytes": feature_count * float_bytes * 2,
        "feature_buffer_bytes": feature_count * float_bytes,
        "activation_buffer_bytes": len(runtime.class_mapping) * float_bytes,
        "output_buffer_bytes": len(runtime.class_mapping) * float_bytes,
        "total_static_ram_bytes": (feature_count + len(runtime.class_mapping) * 2)
        * float_bytes,
        "estimated_stack_usage_bytes": 512,
        "total_generated_source_size_bytes": source_size,
        "estimated_flash_size_bytes": source_size + parameter_count * float_bytes,
        "operation_count_per_inference": operations,
        "notes": "Estimate only; not measured STM32 memory consumption.",
    }
    out = evidence_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "resource_estimate.json").write_text(
        json.dumps(estimate, indent=2), encoding="utf-8"
    )
    (out / "RESOURCE_ESTIMATE.md").write_text(_markdown(estimate), encoding="utf-8")
    return estimate


def _markdown(estimate: dict[str, object]) -> str:
    lines = [
        "# Embedded Resource Estimate",
        "",
        "ESTIMATED SOFTWARE VALUE - NOT MEASURED STM32 MEMORY CONSUMPTION.",
        "",
    ]
    for key, value in estimate.items():
        lines.append(f"- `{key}`: {value}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("config/embedded_export.yaml")
    )
    args = parser.parse_args()
    print(json.dumps(estimate_resources(args.config), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
