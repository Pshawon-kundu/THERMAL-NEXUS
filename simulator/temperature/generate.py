"""Command-line interface for synthetic temperature generation."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from simulator.temperature.config import (
    ConfigurationError,
    load_config,
    scenario_config,
)
from simulator.temperature.generator import generate_run
from simulator.temperature.models import RunArtifacts

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the temperature generator CLI."""

    parser = argparse.ArgumentParser(
        description="Generate Thermal Nexus synthetic temperature data."
    )
    parser.add_argument(
        "--config", required=True, type=Path, help="Path to scenarios YAML."
    )
    parser.add_argument("--scenario", help="Scenario name to generate.")
    parser.add_argument(
        "--all", action="store_true", help="Generate all configured scenarios."
    )
    parser.add_argument(
        "--runs", type=int, default=1, help="Number of runs per scenario."
    )
    parser.add_argument(
        "--output-dir", type=Path, help="Override configured output directory."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        artifacts = run_generation(
            config_path=args.config,
            scenario=args.scenario,
            generate_all=args.all,
            runs=args.runs,
            output_dir=args.output_dir,
        )
    except ConfigurationError as exc:
        LOGGER.error("%s", exc)
        return 2

    LOGGER.info("Generated %s run(s).", len(artifacts))
    for artifact in artifacts:
        LOGGER.info(
            "%s | %s | samples=%s valid=%s | csv=%s",
            artifact.run_id,
            artifact.scenario,
            artifact.sample_count,
            artifact.valid_sample_count,
            artifact.csv_path,
        )
    return 0


def run_generation(
    config_path: Path,
    scenario: str | None,
    generate_all: bool,
    runs: int,
    output_dir: Path | None = None,
) -> list[RunArtifacts]:
    """Validate inputs and generate requested runs."""

    if runs <= 0:
        raise ConfigurationError("--runs must be greater than zero.")
    if generate_all == bool(scenario):
        raise ConfigurationError("Specify exactly one of --scenario or --all.")

    config = load_config(config_path)
    scenario_names = sorted(config.scenarios) if generate_all else [str(scenario)]
    artifacts: list[RunArtifacts] = []

    for scenario_name in scenario_names:
        merged = scenario_config(config, scenario_name)
        destination = output_dir or Path(str(merged["output_dir"]))
        base_seed = int(merged["random_seed"]) + _stable_scenario_offset(scenario_name)
        for run_index in range(runs):
            artifacts.append(
                generate_run(
                    scenario_name=scenario_name,
                    config=merged,
                    run_index=run_index,
                    base_seed=base_seed,
                    output_dir=destination,
                )
            )
    return artifacts


def _stable_scenario_offset(name: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(name))


if __name__ == "__main__":
    sys.exit(main())
