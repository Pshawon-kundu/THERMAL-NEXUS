"""Export frozen feature schema for embedded preparation."""

from __future__ import annotations

from pathlib import Path

import yaml

from ml.inference.model_runtime import ModelRuntime


def export_feature_schema(
    config_path: Path = Path("config/embedded_export.yaml"),
) -> None:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    runtime = ModelRuntime(Path(config["selected_model_path"]))
    output = Path(config["output_path"])
    output.mkdir(parents=True, exist_ok=True)
    names = ",\n".join(f'    "{name}"' for name in runtime.feature_order)
    (output / "thermal_nexus_features.h").write_text(
        f"""#ifndef THERMAL_NEXUS_FEATURES_H
#define THERMAL_NEXUS_FEATURES_H
static const char *THERMAL_NEXUS_FEATURE_NAMES[] = {{
{names}
}};
#endif
""",
        encoding="utf-8",
    )
