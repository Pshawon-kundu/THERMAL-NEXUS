"""SQLite schema for Thermal Nexus offline experiments and live hardware data."""

from __future__ import annotations

SCHEMA_VERSION = 5

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
        node_uid TEXT,
        model_name TEXT,
        model_version TEXT,
        policy_version TEXT,
        protocol_version INTEGER,
        data_source_type TEXT,
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
        sequence_number INTEGER,
        measured_temperature REAL,
        true_temperature REAL,
        sensor_valid INTEGER,
        node_uid TEXT,
        predicted_state TEXT,
        predicted_state_code INTEGER,
        risk_probability REAL,
        applied_state TEXT,
        sampling_interval_seconds REAL,
        transmission_interval_seconds REAL,
        transmission_requested INTEGER,
        transmission_reason TEXT,
        model_latency_ms REAL,
        model_valid INTEGER,
        fallback_status TEXT,
        battery_percentage REAL,
        estimated_energy_joules REAL,
        data_source_type TEXT
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
        out_of_order INTEGER,
        rssi_dbm REAL
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
        node_uid TEXT,
        sequence_number INTEGER,
        measured_temperature REAL,
        predicted_state TEXT,
        risk_probability REAL,
        battery_percentage REAL,
        battery_voltage REAL,
        rssi_dbm REAL,
        sensor_valid INTEGER,
        fault_flags INTEGER,
        packet_latency_ms REAL,
        accepted INTEGER,
        rejection_reason TEXT,
        data_source_type TEXT
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
        node_uid TEXT,
        state TEXT,
        message TEXT,
        acknowledged INTEGER DEFAULT 0,
        resolved INTEGER DEFAULT 0,
        source_event_id TEXT,
        data_source_type TEXT
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
    """
    CREATE TABLE IF NOT EXISTS hardware_runs (
        run_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        firmware_version TEXT,
        operator TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS measurement_traces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL
            REFERENCES hardware_runs(run_id) ON DELETE CASCADE,
        channel TEXT NOT NULL,
        distance_m REAL,
        rssi_dbm REAL,
        per REAL,
        throughput_kbps REAL,
        sampled_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bom_items (
        part_number TEXT NOT NULL,
        run_id TEXT NOT NULL
            REFERENCES hardware_runs(run_id) ON DELETE CASCADE,
        description TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_cost_usd REAL NOT NULL,
        total_cost_usd REAL NOT NULL,
        weight_g REAL NOT NULL,
        volume_cm3 REAL NOT NULL,
        PRIMARY KEY (part_number, run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS physical_measurements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL
            REFERENCES hardware_runs(run_id) ON DELETE CASCADE,
        sensor_id TEXT NOT NULL,
        setpoint_c REAL NOT NULL,
        measured_c REAL NOT NULL,
        error_c REAL NOT NULL,
        sampled_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gps_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        received_at REAL NOT NULL,
        transport_seq INTEGER,
        gps_valid INTEGER,
        latitude REAL,
        longitude REAL,
        gps_date TEXT,
        gps_utc_time TEXT,
        satellites INTEGER,
        hdop REAL,
        rssi_dbm REAL,
        snr_db REAL,
        signal_quality INTEGER,
        unique_rx INTEGER,
        duplicate_count INTEGER,
        estimated_missing INTEGER,
        malformed_count INTEGER,
        reception_rate REAL,
        raw_line TEXT,
        data_source_type TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stm_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        received_at REAL NOT NULL,
        transport_seq INTEGER,
        stm_sample_seq INTEGER,
        ntc1_temp REAL,
        ntc2_temp REAL,
        ntc3_temp REAL,
        ntc4_temp REAL,
        ntc5_temp REAL,
        ntc6_temp REAL,
        ntc7_temp REAL,
        ntc8_temp REAL,
        ntc1_raw INTEGER,
        ntc2_raw INTEGER,
        ntc3_raw INTEGER,
        ntc4_raw INTEGER,
        ntc5_raw INTEGER,
        ntc6_raw INTEGER,
        ntc7_raw INTEGER,
        ntc8_raw INTEGER,
        gy1_valid INTEGER,
        gy1_temp REAL,
        gy1_humidity REAL,
        gy2_valid INTEGER,
        gy2_temp REAL,
        gy2_humidity REAL,
        rssi_dbm REAL,
        snr_db REAL,
        signal_quality INTEGER,
        unique_rx INTEGER,
        duplicate_count INTEGER,
        estimated_missing INTEGER,
        malformed_count INTEGER,
        reception_rate REAL,
        raw_line TEXT,
        data_source_type TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS receiver_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        received_at REAL NOT NULL,
        event_type TEXT NOT NULL,
        packet_type TEXT,
        transport_seq INTEGER,
        rssi_dbm REAL,
        snr_db REAL,
        signal_quality INTEGER,
        details TEXT,
        raw_line TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS serial_status (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        port TEXT,
        baud INTEGER,
        connected INTEGER,
        last_line_at REAL,
        last_valid_packet_at REAL,
        last_error TEXT,
        updated_at REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS telemetry_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        received_at REAL NOT NULL,
        seq INTEGER,
        time_sec INTEGER,
        gps_valid INTEGER,
        latitude REAL,
        longitude REAL,
        satellites INTEGER,
        digital_top_temp REAL,
        digital_bottom_temp REAL,
        ntc1_temp REAL,
        ntc2_temp REAL,
        ntc3_temp REAL,
        ntc4_temp REAL,
        ntc5_temp REAL,
        ntc6_temp REAL,
        ntc7_temp REAL,
        ntc8_temp REAL,
        rssi_dbm REAL,
        snr_db REAL,
        signal_quality INTEGER,
        unique_rx INTEGER,
        duplicate_count INTEGER,
        estimated_missing INTEGER,
        malformed_count INTEGER,
        reception_rate REAL,
        raw_line TEXT,
        data_source_type TEXT
    )
    """,
]  # noqa: E501

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
    (
        "CREATE INDEX IF NOT EXISTS idx_measurement_traces_run "
        "ON measurement_traces(run_id, distance_m)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_physical_measurements_run "
        "ON physical_measurements(run_id, setpoint_c)"
    ),
    ("CREATE INDEX IF NOT EXISTS idx_bom_items_run " "ON bom_items(run_id)"),
    (
        "CREATE INDEX IF NOT EXISTS idx_hardware_runs_source "
        "ON hardware_runs(source, started_at)"
    ),
    "CREATE INDEX IF NOT EXISTS idx_gps_readings_received_at ON gps_readings(received_at)",
    "CREATE INDEX IF NOT EXISTS idx_gps_readings_transport_seq ON gps_readings(transport_seq)",
    "CREATE INDEX IF NOT EXISTS idx_stm_samples_received_at ON stm_samples(received_at)",
    "CREATE INDEX IF NOT EXISTS idx_stm_samples_transport_seq ON stm_samples(transport_seq)",
    "CREATE INDEX IF NOT EXISTS idx_stm_samples_stm_sample_seq ON stm_samples(stm_sample_seq)",
    "CREATE INDEX IF NOT EXISTS idx_receiver_events_received_at ON receiver_events(received_at)",
    "CREATE INDEX IF NOT EXISTS idx_telemetry_readings_received_at ON telemetry_readings(received_at)",
    "CREATE INDEX IF NOT EXISTS idx_telemetry_readings_seq ON telemetry_readings(seq)",
]
