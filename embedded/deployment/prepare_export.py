"""One-command embedded export preparation."""

from __future__ import annotations

import json

from embedded.deployment.estimate_resources import estimate_resources
from embedded.deployment.export_feature_schema import export_feature_schema
from embedded.deployment.export_manifest import create_manifest
from embedded.deployment.export_model import export_model
from embedded.deployment.export_policy import export_policy
from embedded.deployment.export_preprocessing import export_preprocessing
from embedded.deployment.export_protocol import export_protocol
from embedded.deployment.generate_golden_vectors import generate_golden_vectors


def prepare_export() -> dict[str, object]:
    """Run all embedded preparation steps."""

    manifest = create_manifest()
    model = export_model()
    export_preprocessing()
    export_feature_schema()
    export_policy()
    export_protocol()
    vectors = generate_golden_vectors()
    resources = estimate_resources()
    return {
        "manifest_model": manifest["model_type"],
        "exported_model": model["model_type"],
        "golden_vectors": len(vectors),
        "resource_value_type": resources["value_type"],
    }


if __name__ == "__main__":
    print(json.dumps(prepare_export(), indent=2))
