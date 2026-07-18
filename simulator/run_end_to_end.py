"""End-to-end Thermal Nexus software simulation CLI."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from analysis.runtime_metrics import summarize_mode, write_runtime_report
from ml.features.extract_features import load_feature_config
from ml.inference.model_runtime import ModelRuntime
from simulator.radio.channel import RadioChannel, load_radio_config
from simulator.reader.reader import VirtualReader
from simulator.sensor_node.config import load_runtime_policy
from simulator.sensor_node.modes import OperatingMode
from simulator.sensor_node.node import VirtualSensorNode
from simulator.temperature.generate import run_generation

LOGGER = logging.getLogger(__name__)


MODE_MAP = {
    "fixed": OperatingMode.MODE_A_FIXED,
    "rule_based": OperatingMode.MODE_B_RULE_BASED,
    "ml": OperatingMode.MODE_C_TINYML_SIMULATION,
}


def main(argv: list[str] | None = None) -> int:
    """Run an end-to-end software demonstration."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--modes", nargs="+", default=["fixed", "rule_based", "ml"])
    parser.add_argument("--radio-config", type=Path, required=True)
    parser.add_argument("--policy-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_end_to_end(
        scenario=args.scenario,
        runs=args.runs,
        modes=args.modes,
        radio_config_path=args.radio_config,
        policy_config_path=args.policy_config,
        output_dir=args.output,
    )
    return 0


def run_end_to_end(
    scenario: str,
    runs: int,
    modes: list[str],
    radio_config_path: Path,
    policy_config_path: Path,
    output_dir: Path,
) -> list[dict[str, object]]:
    """Execute all requested modes against the same synthetic run."""

    output_dir.mkdir(parents=True, exist_ok=True)
    generated = run_generation(
        config_path=Path("config/scenarios.yaml"),
        scenario=scenario,
        generate_all=False,
        runs=runs,
        output_dir=output_dir / "thermal_input",
    )
    thermal_frame = pd.read_csv(generated[0].csv_path)
    policy = load_runtime_policy(policy_config_path)
    feature_config = load_feature_config(Path("config/features.yaml"))
    metrics: list[dict[str, object]] = []
    for index, mode_name in enumerate(modes, start=1):
        mode = MODE_MAP[mode_name]
        mode_dir = output_dir / mode_name
        mode_dir.mkdir(parents=True, exist_ok=True)
        runtime = (
            ModelRuntime(Path("ml/models/selected"))
            if mode == OperatingMode.MODE_C_TINYML_SIMULATION
            else None
        )
        node = VirtualSensorNode(
            node_id=index,
            operating_mode=mode,
            policy_config=policy,
            feature_config=feature_config,
            model_runtime=runtime,
        )
        result = node.run(thermal_frame)
        radio = RadioChannel(load_radio_config(radio_config_path))
        reader = VirtualReader()
        requested = result.decisions["transmission_requested"].astype(bool)
        send_times = result.decisions[requested]["timestamp_seconds"].tolist()
        for packet, send_time in zip(result.packets, send_times, strict=True):
            radio.transmit(packet, float(send_time))
        for delivery in radio.flush():
            reader.receive(delivery)
        reader.check_stale_nodes(
            float(result.decisions["timestamp_seconds"].max()) + 601
        )
        result.decisions.to_csv(mode_dir / "node_decisions.csv", index=False)
        pd.DataFrame(radio.events).to_csv(mode_dir / "radio_events.csv", index=False)
        reader.storage.write(mode_dir)
        metrics.append(
            summarize_mode(
                mode_name,
                result.decisions,
                pd.DataFrame(radio.events),
                pd.DataFrame(reader.storage.accepted_records),
                pd.DataFrame(reader.storage.alerts),
            )
        )
        LOGGER.info("%s completed with %s packets.", mode_name, len(result.packets))
    write_runtime_report(metrics, output_dir)
    return metrics


if __name__ == "__main__":
    sys.exit(main())
