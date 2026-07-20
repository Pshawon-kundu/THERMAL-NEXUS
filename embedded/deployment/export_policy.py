"""Export runtime policy constants for embedded preparation."""

from __future__ import annotations

from pathlib import Path

from simulator.sensor_node.config import load_runtime_policy


def export_policy(
    policy_path: Path = Path("config/runtime_policy.yaml"),
    output_dir: Path = Path("embedded/generated"),
) -> None:
    config = load_runtime_policy(policy_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "#ifndef THERMAL_NEXUS_POLICY_H",
        "#define THERMAL_NEXUS_POLICY_H",
        "/* Preliminary software policy constants, not final hardware settings. */",
    ]
    for name, policy in config.states.items():
        prefix = f"THERMAL_NEXUS_{name}"
        lines.append(
            f"#define {prefix}_SAMPLE_SECONDS {int(policy.sampling_interval_seconds)}"
        )
        lines.append(
            f"#define {prefix}_TRANSMIT_SECONDS "
            f"{int(policy.transmission_interval_seconds)}"
        )
    lines.append("#endif")
    (output_dir / "thermal_nexus_policy.h").write_text(
        "\n".join(lines), encoding="utf-8"
    )
