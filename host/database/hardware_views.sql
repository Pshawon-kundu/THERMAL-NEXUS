-- Hardware-phase views.
-- Re-applied on every host.database.migrations.initialize_database() call.

CREATE VIEW IF NOT EXISTS v_hardware_runs AS
SELECT
    hr.run_id,
    hr.source,
    hr.firmware_version,
    hr.operator,
    hr.started_at,
    hr.ended_at,
    hr.notes,
    (SELECT COUNT(*) FROM measurement_traces mt WHERE mt.run_id = hr.run_id) AS trace_count,
    (SELECT COUNT(*) FROM physical_measurements pm WHERE pm.run_id = hr.run_id) AS accuracy_count,
    (SELECT COUNT(*) FROM bom_items bi WHERE bi.run_id = hr.run_id) AS bom_count
FROM hardware_runs hr;

CREATE VIEW IF NOT EXISTS v_hardware_range AS
SELECT
    mt.run_id,
    mt.channel,
    mt.distance_m,
    mt.rssi_dbm,
    mt.per,
    mt.throughput_kbps,
    mt.sampled_at
FROM measurement_traces mt;

CREATE VIEW IF NOT EXISTS v_hardware_accuracy AS
SELECT
    pm.run_id,
    pm.sensor_id,
    pm.setpoint_c,
    pm.measured_c,
    pm.error_c,
    ABS(pm.error_c) AS abs_error_c,
    pm.sampled_at
FROM physical_measurements pm;

CREATE VIEW IF NOT EXISTS v_hardware_bom AS
SELECT
    bi.run_id,
    bi.part_number,
    bi.description,
    bi.quantity,
    bi.unit_cost_usd,
    bi.total_cost_usd,
    bi.weight_g,
    bi.volume_cm3
FROM bom_items bi;

CREATE VIEW IF NOT EXISTS v_hardware_kpi AS
SELECT
    hr.run_id,
    hr.source,
    hr.firmware_version,
    hr.started_at,
    (SELECT MAX(mt.distance_m) FROM measurement_traces mt
       WHERE mt.run_id = hr.run_id AND mt.per < 0.5) AS range_m,
    (SELECT MAX(ABS(pm.error_c)) FROM physical_measurements pm
       WHERE pm.run_id = hr.run_id) AS accuracy_max_abs_error_c,
    (SELECT AVG(ABS(pm.error_c)) FROM physical_measurements pm
       WHERE pm.run_id = hr.run_id) AS accuracy_mean_abs_error_c,
    (SELECT SUM(bi.total_cost_usd) FROM bom_items bi
       WHERE bi.run_id = hr.run_id) AS bom_total_cost_usd,
    (SELECT SUM(bi.weight_g * bi.quantity) FROM bom_items bi
       WHERE bi.run_id = hr.run_id) AS bom_total_weight_g,
    (SELECT SUM(bi.volume_cm3 * bi.quantity) FROM bom_items bi
       WHERE bi.run_id = hr.run_id) AS bom_total_volume_cm3
FROM hardware_runs hr;
