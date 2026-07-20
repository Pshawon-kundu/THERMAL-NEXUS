"""Compatible experiment KPI comparison."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from host.database.connection import DEFAULT_DATABASE_PATH
from host.database.repository import ExperimentRepository


class ComparisonError(ValueError):
    """Raised when experiments cannot be compared."""


def compare_experiments(
    experiment_ids: list[str],
    database_path: Path = DEFAULT_DATABASE_PATH,
    output_root: Path = Path("evidence/kpi/comparisons"),
) -> Path:
    """Compare compatible experiments and generate reports."""

    repository = ExperimentRepository(database_path)
    metadata = [repository.get_experiment(item) for item in experiment_ids]
    if any(item is None for item in metadata):
        raise ComparisonError("One or more experiments were not found.")
    scenarios = {item["scenario"] for item in metadata if item is not None}
    run_ids = {item["run_id"] for item in metadata if item is not None}
    if len(scenarios) > 1 or len(run_ids) > 1:
        raise ComparisonError("Experiments are not compatible for comparison.")
    rows = []
    for item in metadata:
        assert item is not None
        for kpi in repository.get_kpi_results(str(item["experiment_id"])):
            rows.append(
                {
                    "experiment_id": item["experiment_id"],
                    "mode": item["operating_mode"],
                    "metric_name": kpi["metric_name"],
                    "metric_value": kpi["metric_value"],
                    "unit": kpi["unit"],
                    "value_type": kpi["value_type"],
                }
            )
    comparison_id = f"comparison_{uuid4().hex[:12]}"
    output_dir = output_root / comparison_id
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(output_dir / "comparison.csv", index=False)
    (output_dir / "comparison.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    report = [
        "# Experiment Comparison Report",
        "",
        "SIMULATED SOFTWARE DATA - NOT PHYSICAL HARDWARE RESULTS",
        "",
        f"Experiments compared: {len(experiment_ids)}",
        f"Scenario: {next(iter(scenarios)) if scenarios else ''}",
        "",
        "Do not infer statistical significance from a single run.",
    ]
    (output_dir / "COMPARISON_REPORT.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    (output_dir / "COMPARISON_REPORT.html").write_text(
        "<html><body><pre>" + "\n".join(report) + "</pre></body></html>",
        encoding="utf-8",
    )
    return output_dir
