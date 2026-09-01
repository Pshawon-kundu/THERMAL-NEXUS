#!/usr/bin/env bash
# One-shot macOS launcher for the full hardware-phase pipeline.
#   1. Migrate the database to v2.
#   2. Run the simulated hardware campaign.
#   3. Verify Phase-2 KPI thresholds.
#   4. Refresh KPI reports so the Streamlit tab picks them up.
#
# Usage:
#   bash tools/run_hardware_phase_macos.sh            # simulated
#   bash tools/run_hardware_phase_macos.sh measured   # measured (Phase 7)

set -euo pipefail

cd "$(dirname "$0")/.."

SOURCE="${1:-simulated}"
DB="host/database/thermal_nexus.db"
CONFIG="config/hardware_demo.yaml"
OUTPUT="evidence/hardware/run_$(date +%Y%m%d%H%M%S)"

echo "==[1/4]== Migrating database → schema_version=2"
.venv/bin/python -m host.database.migrations

echo "==[2/4]== Running hardware campaign: source=$SOURCE output=$OUTPUT"
.venv/bin/python -m simulator.hardware.run_hardware_demo \
    --source "$SOURCE" \
    --config "$CONFIG" \
    --output "$OUTPUT" \
    --database "$DB"

echo "==[3/4]== Verifying Phase-2 KPI thresholds"
.venv/bin/python - <<'PY'
import sqlite3, sys
con = sqlite3.connect("host/database/thermal_nexus.db")
con.row_factory = sqlite3.Row
row = con.execute("""
    SELECT
        hr.run_id,
        (SELECT MAX(mt.distance_m) FROM measurement_traces mt
            WHERE mt.run_id = hr.run_id AND mt.per < 0.5) AS range_m,
        (SELECT MAX(ABS(pm.error_c)) FROM physical_measurements pm
            WHERE pm.run_id = hr.run_id) AS accuracy_max_error,
        (SELECT SUM(bi.total_cost_usd) FROM bom_items bi
            WHERE bi.run_id = hr.run_id) AS bom_cost,
        (SELECT SUM(bi.weight_g * bi.quantity) FROM bom_items bi
            WHERE bi.run_id = hr.run_id) AS weight_g,
        (SELECT SUM(bi.volume_cm3 * bi.quantity) FROM bom_items bi
            WHERE bi.run_id = hr.run_id) AS volume_cm3
    FROM hardware_runs hr
    ORDER BY hr.started_at DESC
    LIMIT 1;
""").fetchone()
if row is None:
    sys.exit("verify_hardware_phase: no hardware runs in DB")

targets = {"range_m": (60.0, ">="), "accuracy_max_error": (0.5, "<="),
           "bom_cost": (75.0, "<="), "weight_g": (80.0, "<="), "volume_cm3": (250.0, "<=")}
ok = True
for key, (limit, op) in targets.items():
    value = row[key]
    passed = value is not None and (
        (op == ">=" and value >= limit) or
        (op == "<=" and value <= limit)
    )
    flag = "✅" if passed else "⚠️ "
    print(f"  {flag} {key:20s} {value!r:>10}  {op} {limit}")
    ok = ok and passed

if ok:
    print("[verify_hardware_phase] ✅ All Phase-2 KPI targets met.")
else:
    print("[verify_hardware_phase] ⚠️  One or more thresholds missed; review before sign-off.")
PY

echo "==[4/4]== Regenerating KPI reports"
.venv/bin/python -m analysis.kpi_reports --database "$DB"

echo "Done. Reload the Hardware tab in the Streamlit dashboard (localhost:8501)."
