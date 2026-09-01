"""Validation helpers for KPI reports."""

from __future__ import annotations


def assert_estimated_energy_labeled(kpis: list[dict[str, object]]) -> None:
    """Ensure every estimated energy KPI is labeled correctly."""

    for item in kpis:
        if str(item["metric_name"]).startswith("estimated_"):
            if item["value_type"] != "ESTIMATED_SOFTWARE_VALUE":
                raise ValueError(f"Energy KPI not labeled: {item['metric_name']}")
