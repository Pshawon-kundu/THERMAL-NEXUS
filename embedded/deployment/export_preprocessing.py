"""Export preprocessing interface for embedded preparation."""

from __future__ import annotations

from pathlib import Path

import yaml

from ml.inference.model_runtime import ModelRuntime


def export_preprocessing(
    config_path: Path = Path("config/embedded_export.yaml"),
) -> None:
    """Generate portable preprocessing interface files."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    runtime = ModelRuntime(Path(config["selected_model_path"]))
    output = Path(config["output_path"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "thermal_nexus_preprocessing.h").write_text(
        """#ifndef THERMAL_NEXUS_PREPROCESSING_H
#define THERMAL_NEXUS_PREPROCESSING_H
#include "thermal_nexus_model.h"
void thermal_nexus_preprocess(
    const float raw[THERMAL_NEXUS_FEATURE_COUNT],
    float processed[THERMAL_NEXUS_FEATURE_COUNT]);
#endif
""",
        encoding="utf-8",
    )
    (output / "thermal_nexus_preprocessing.c").write_text(
        """#include "thermal_nexus_preprocessing.h"
void thermal_nexus_preprocess(
    const float raw[THERMAL_NEXUS_FEATURE_COUNT],
    float processed[THERMAL_NEXUS_FEATURE_COUNT]) {
    for (int i = 0; i < THERMAL_NEXUS_FEATURE_COUNT; ++i) {
        processed[i] = raw[i];
    }
}
""",
        encoding="utf-8",
    )
    if not runtime.loaded:
        raise RuntimeError(f"Selected model unavailable: {runtime.load_error}")
