"""Parameterized SQL queries for offline experiment data."""

from __future__ import annotations

LIST_EXPERIMENTS = """
SELECT * FROM experiments
WHERE (? IS NULL OR scenario = ?)
  AND (? IS NULL OR operating_mode = ?)
ORDER BY imported_at DESC
"""

GET_EXPERIMENT = "SELECT * FROM experiments WHERE experiment_id = ?"
GET_NODE_DECISIONS = (
    "SELECT * FROM node_decisions WHERE experiment_id = ? ORDER BY sequence_index"
)
GET_RADIO_EVENTS = (
    "SELECT * FROM radio_events WHERE experiment_id = ? ORDER BY timestamp, id"
)
GET_READER_RECORDS = (
    "SELECT * FROM reader_records WHERE experiment_id = ? ORDER BY received_at, id"
)
GET_ALERTS = "SELECT * FROM alerts WHERE experiment_id = ? ORDER BY timestamp, id"
GET_KPIS = "SELECT * FROM kpi_results WHERE experiment_id = ? ORDER BY metric_name"

LIST_SCENARIOS = (
    "SELECT DISTINCT scenario FROM experiments "
    "WHERE scenario IS NOT NULL ORDER BY scenario"
)
LIST_MODEL_VERSIONS = (
    "SELECT DISTINCT model_version FROM experiments "
    "WHERE model_version != '' ORDER BY model_version"
)
LIST_POLICY_VERSIONS = (
    "SELECT DISTINCT policy_version FROM experiments ORDER BY policy_version"
)

PACKET_COUNTS = """
SELECT
  SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END) AS accepted,
  SUM(CASE WHEN accepted = 0 THEN 1 ELSE 0 END) AS rejected
FROM reader_records
WHERE experiment_id = ?
"""

MODE_COMPARISON = """
SELECT e.operating_mode, k.metric_name, k.metric_value, k.unit, k.value_type
FROM experiments e
JOIN kpi_results k ON e.experiment_id = k.experiment_id
WHERE e.scenario = ?
ORDER BY e.operating_mode, k.metric_name
"""
