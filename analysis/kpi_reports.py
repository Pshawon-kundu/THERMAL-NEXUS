"""KPI report generation."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from analysis.kpi_engine import calculate_kpis
from host.database.connection import DEFAULT_DATABASE_PATH
from host.database.repository import ExperimentRepository


def generate_kpi_report(
    experiment_id: str,
    database_path: Path = DEFAULT_DATABASE_PATH,
    output_root: Path = Path("evidence/kpi"),
) -> Path:
    """Generate CSV, JSON, Markdown, and HTML KPI reports."""

    repository = ExperimentRepository(database_path)
    metadata = repository.get_experiment(experiment_id)
    if metadata is None:
        raise ValueError(f"Experiment not found: {experiment_id}")
    kpis = calculate_kpis(experiment_id, database_path)
    output_dir = output_root / _safe_id(experiment_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(kpis)
    frame.to_csv(output_dir / "kpi_results.csv", index=False)
    (output_dir / "kpi_results.json").write_text(
        json.dumps(kpis, indent=2), encoding="utf-8"
    )
    markdown = _markdown(metadata, frame)
    (output_dir / "KPI_REPORT.md").write_text(markdown, encoding="utf-8")
    (output_dir / "KPI_REPORT.html").write_text(
        "<html><body><pre>" + markdown + "</pre></body></html>",
        encoding="utf-8",
    )
    return output_dir


def _markdown(metadata: dict[str, object], frame: pd.DataFrame) -> str:
    rows = [
        "# KPI Report",
        "",
        "SIMULATED SOFTWARE DATA - NOT PHYSICAL HARDWARE RESULTS",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Experiment: `{metadata['experiment_id']}`",
        f"Scenario: `{metadata['scenario']}`",
        f"Operating mode: `{metadata['operating_mode']}`",
        f"Model version: `{metadata['model_version']}`",
        f"Policy version: `{metadata['policy_version']}`",
        "",
        "| metric | value | unit | value_type |",
        "| --- | ---: | --- | --- |",
    ]
    for _, item in frame.iterrows():
        rows.append(
            f"| {item['metric_name']} | {item['metric_value']} | "
            f"{item['unit']} | {item['value_type']} |"
        )
    rows.extend(
        [
            "",
            "Energy KPIs are ESTIMATED_SOFTWARE_VALUE and are not measured Wh.",
        ]
    )
    return "\n".join(rows)


def _safe_id(value: str) -> str:
    return value.replace(":", "_").replace("\\", "_").replace("/", "_")


def main() -> int:
    """Generate KPI reports for all or one imported experiment."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--experiment-id")
    args = parser.parse_args()
    repository = ExperimentRepository(args.database)
    experiments = (
        [repository.get_experiment(args.experiment_id)]
        if args.experiment_id
        else repository.list_experiments()
    )
    generated = []
    for experiment in experiments:
        if experiment:
            generated.append(
                str(generate_kpi_report(experiment["experiment_id"], args.database))
            )
    print(json.dumps({"generated": generated}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
