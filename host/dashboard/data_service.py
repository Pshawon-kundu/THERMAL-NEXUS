"""Data service used by the offline dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from host.database.connection import DEFAULT_DATABASE_PATH
from host.database.migrations import initialize_database
from host.database.repository import ExperimentRepository


class DashboardDataService:
    """Reader-friendly dashboard queries."""

    def __init__(self, database_path: Path = DEFAULT_DATABASE_PATH) -> None:
        initialize_database(database_path)
        self.repository = ExperimentRepository(database_path)

    def system_overview(self) -> dict[str, Any]:
        """Return high-level system metrics, handling empty DBs."""

        experiments = self.repository.list_experiments()
        accepted = 0
        rejected = 0
        alerts = 0
        nodes: set[int] = set()
        for experiment in experiments:
            counts = self.repository.count_packets(experiment["experiment_id"])
            accepted += counts["accepted"]
            rejected += counts["rejected"]
            alerts += len(self.repository.get_alerts(experiment["experiment_id"]))
            if experiment["node_id"] is not None:
                nodes.add(int(experiment["node_id"]))
        latest = experiments[0]["experiment_id"] if experiments else None
        model_versions = self.repository.list_model_versions()
        return {
            "experiment_count": len(experiments),
            "scenario_count": len(self.repository.list_available_scenarios()),
            "node_count": len(nodes),
            "accepted_packets": accepted,
            "rejected_packets": rejected,
            "unresolved_alerts": alerts,
            "selected_model": model_versions[-1] if model_versions else "",
            "model_version": model_versions[-1] if model_versions else "",
            "policy_version": "runtime_policy_v1",
            "protocol_version": 1,
            "latest_experiment": latest,
            "limitations_notice": "SYNTHETIC REPLAY DATA - NOT LIVE HARDWARE",
        }

    def experiments(self) -> list[dict[str, Any]]:
        return self.repository.list_experiments()

    def experiment_details(self, experiment_id: str) -> dict[str, Any] | None:
        return self.repository.get_experiment(experiment_id)

    def mode_comparison(self) -> list[dict[str, Any]]:
        rows = []
        for experiment in self.repository.list_experiments():
            for kpi in self.repository.get_kpi_results(experiment["experiment_id"]):
                rows.append({**experiment, **kpi})
        return rows
