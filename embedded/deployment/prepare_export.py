"""One-command embedded export preparation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from embedded.deployment.estimate_resources import estimate_resources
from embedded.deployment.export_feature_schema import export_feature_schema
from embedded.deployment.export_manifest import create_manifest
from embedded.deployment.export_model import export_model
from embedded.deployment.export_policy import export_policy
from embedded.deployment.export_preprocessing import export_preprocessing
from embedded.deployment.export_protocol import export_protocol
from embedded.deployment.generate_golden_vectors import generate_golden_vectors


def prepare_export(
    config_path: Path = Path("config/embedded_export.yaml"),
    golden_source_csv: Path = Path("ml/data/splits/validation.csv"),
    golden_output_dir: Path = Path("embedded/golden_vectors"),
    resource_evidence_dir: Path = Path("evidence/embedded"),
) -> dict[str, object]:
    """Run all embedded preparation steps."""

    config_path = Path(config_path)
    golden_source_csv = Path(golden_source_csv)
    golden_output_dir = Path(golden_output_dir)
    resource_evidence_dir = Path(resource_evidence_dir)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    generated_output_dir = Path(config["output_path"])
    manifest = create_manifest(config_path)
    model = export_model(config_path)
    export_preprocessing(config_path)
    export_feature_schema(config_path)
    export_policy(output_dir=generated_output_dir)
    export_protocol(generated_output_dir)
    vectors = generate_golden_vectors(config_path, golden_source_csv, golden_output_dir)
    resources = estimate_resources(config_path, resource_evidence_dir)
    return {
        "manifest_model": manifest["model_type"],
        "exported_model": model["model_type"],
        "golden_vectors": len(vectors),
        "resource_value_type": resources["value_type"],
    }


if __name__ == "__main__":
    print(json.dumps(prepare_export(), indent=2))
