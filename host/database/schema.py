"""SQLite schema for Thermal Nexus offline experiments."""

from __future__ import annotations

SCHEMA_VERSION = 1

DDL = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS experiments (
        experiment_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        source_type TEXT NOT NULL,
        scenario TEXT,
        operating_mode TEXT NOT NULL,
        run_id TEXT,
        node_id INTEGER,
        model_name TEXT,
        model_version TEXT,
        policy_version TEXT,
        protocol_version INTEGER,
        simulation_seed INTEGER,
        started_at TEXT,
        ended_at TEXT,
        duration_seconds REAL,
        status TEXT NOT NULL,
        notes TEXT,
        source_directory TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        UNIQUE(source_directory, operating_mode)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS node_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL
            REFERENCES experiments(experiment_id) ON DELETE CASCADE,
        timestamp TEXT,
        sequence_index INTEGER,
        measured_temperature REAL,
        true_temperature REAL,
        sensor_valid INTEGER,
        predicted_state TEXT,
        predicted_state_code INTEGER,
        risk_probability REAL,
        applied_state TEXT,
        sampling_interval_seconds REAL,
        transmission_interval_seconds REAL,
        transmission_requested INTEGER,
        transmission_reason TEXT,
        model_latency_ms REAL,
        fallback_status TEXT,
        battery_percentage REAL,
        estimated_energy_joules REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS radio_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL
            REFERENCES experiments(experiment_id) ON DELETE CASCADE,
        timestamp REAL,
        sequence_number INTEGER,
        event_type TEXT,
        retry_number INTEGER,
        delivery_latency_ms REAL,
        packet_size_bytes INTEGER,
        drop_reason TEXT,
        corrupted INTEGER,
        duplicated INTEGER,
        out_of_order INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reader_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL
            REFERENCES experiments(experiment_id) ON DELETE CASCADE,
        timestamp REAL,
        received_at REAL,
        node_id INTEGER,
        sequence_number INTEGER,
        measured_temperature REAL,
        predicted_state TEXT,
        risk_probability REAL,
        battery_percentage REAL,
        sensor_valid INTEGER,
        fault_flags INTEGER,
        packet_latency_ms REAL,
        accepted INTEGER,
        rejection_reason TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL
            REFERENCES experiments(experiment_id) ON DELETE CASCADE,
        timestamp REAL,
        alert_type TEXT,
        severity TEXT,
        node_id INTEGER,
        state TEXT,
        message TEXT,
        acknowledged INTEGER DEFAULT 0,
        resolved INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kpi_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL
            REFERENCES experiments(experiment_id) ON DELETE CASCADE,
        generated_at TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        unit TEXT,
        value_type TEXT,
        method TEXT,
        notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL
            REFERENCES experiments(experiment_id) ON DELETE CASCADE,
        artifact_type TEXT NOT NULL,
        file_path TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_experiments_run_id ON experiments(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_experiments_mode ON experiments(operating_mode)",
    "CREATE INDEX IF NOT EXISTS idx_experiments_node ON experiments(node_id)",
    (
        "CREATE INDEX IF NOT EXISTS idx_node_decisions_exp_time "
        "ON node_decisions(experiment_id, timestamp)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_radio_events_exp_time "
        "ON radio_events(experiment_id, timestamp)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_reader_records_exp_node "
        "ON reader_records(experiment_id, node_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_alerts_exp_time "
        "ON alerts(experiment_id, timestamp)"
    ),
]
