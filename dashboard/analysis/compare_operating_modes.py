"""CLI for comparing generated end-to-end operating-mode outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from analysis.runtime_metrics import summarize_mode, write_runtime_report


def compare_modes(output_dir: Path, modes: list[str]) -> list[dict[str, object]]:
    """Compare saved mode outputs in an end-to-end directory."""

    metrics = []
    for mode in modes:
        mode_dir = output_dir / mode
        metrics.append(
            summarize_mode(
                mode=mode,
                decisions=pd.read_csv(mode_dir / "node_decisions.csv"),
                radio_events=(
                    pd.read_csv(mode_dir / "radio_events.csv")
                    if (mode_dir / "radio_events.csv").exists()
                    else pd.DataFrame()
                ),
                reader_records=(
                    pd.read_csv(mode_dir / "reader_records.csv")
                    if (mode_dir / "reader_records.csv").exists()
                    else pd.DataFrame()
                ),
                alerts=(
                    pd.read_csv(mode_dir / "alerts.csv")
                    if (mode_dir / "alerts.csv").exists()
                    else pd.DataFrame()
                ),
            )
        )
    write_runtime_report(metrics, output_dir)
    return metrics


def main(argv: list[str] | None = None) -> int:
    """Run the comparison CLI."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--modes", nargs="+", default=["fixed", "rule_based", "ml"])
    args = parser.parse_args(argv)
    metrics = compare_modes(args.output, args.modes)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
