"""Hardware-phase end-to-end CLI.

Run a complete simulated (or measured, when wired up in Phase 7) hardware
campaign and persist everything to disk + SQLite:

  range test       → evidence/hardware/<run>/range_test.csv
                    + measurement_traces table
  accuracy test    → evidence/hardware/<run>/accuracy_test.csv
                    + physical_measurements table
  BoM              → evidence/hardware/<run>/bom.csv
                    + bom_items table
  energy estimate  → evidence/hardware/<run>/summary.json

Run with:

    python -m simulator.hardware.run_hardware_demo \\
        --source simulated \\
        --config config/hardware_demo.yaml \\
        --output evidence/hardware/run_001

When real hardware is available, swap ``--source measured`` and replace
the four ``measure_*`` helpers in ``tmp117.py`` / ``xbee.py`` with calls
to the reader firmare. Nothing else in the pipeline changes.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import yaml
from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.schema import SCHEMA_VERSION

from .accuracy_test import persist_accuracy_test, run_accuracy_test
from .bom import DEFAULT_BOM, persist_bom_to_db, summarise_bom
from .range_test import persist_range_test, run_range_test
from .stm32 import STM32Config, energy_wh_per_event
from .tmp117 import TMP117Config
from .xbee import XBeeConfig

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_ROOT = Path("evidence/hardware")
DEFAULT_CONFIG_PATH = Path("config/hardware_demo.yaml")
DEFAULT_DATABASE = DEFAULT_DATABASE_PATH


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simulator.hardware.run_hardware_demo",
        description="Run a simulated or measured Thermal Nexus hardware campaign.",
    )
    parser.add_argument(
        "--source",
        choices=("simulated", "measured"),
        default="simulated",
        help="Data source: 'simulated' uses datasheet-driven models, 'measured' reads from real firmware.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="YAML config (default: config/hardware_demo.yaml).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: evidence/hardware/<run_id>).",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="SQLite database path (default: host/database/thermal_nexus.db).",
    )
    parser.add_argument(
        "--operator",
        default="simulator",
        help="Operator name recorded in hardware_runs.",
    )
    parser.add_argument(
        "--firmware-version",
        default="0.0.0-simulated",
        help="Firmware version recorded in hardware_runs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _ensure_schema(con) -> None:
    cur = con.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
    if cur is None or cur["version"] < SCHEMA_VERSION:
        raise RuntimeError(
            "Database is below the required schema_version. "
            "Run `python -m host.database.migrations` first."
        )


def _register_hardware_run(con, *, run_id: str, source: str, firmware: str,
                           operator: str, started_at: str, notes: str) -> None:
    con.execute(
        """
        INSERT INTO hardware_runs (
            run_id, source, firmware_version, operator, started_at, notes
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, source, firmware, operator, started_at, notes),
    )


def _finalize_hardware_run(con, run_id: str, ended_at: str) -> None:
    con.execute(
        "UPDATE hardware_runs SET ended_at = ? WHERE run_id = ?",
        (ended_at, run_id),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = _load_yaml(args.config)
    tmp_cfg = TMP117Config(**(cfg.get("tmp117") or {}))
    xbee_cfg = XBeeConfig(**(cfg.get("xbee") or {}))
    mcu_cfg = STM32Config(**(cfg.get("stm32") or {}))

    started_at = datetime.now(UTC).isoformat()
    run_id = f"hw_{started_at.replace(':', '').replace('-', '').replace('.', '')}"

    output_dir = args.output or (DEFAULT_OUTPUT_ROOT / run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Hardware campaign run_id=%s source=%s output=%s", run_id, args.source, output_dir)

    # --- Range test ----------------------------------------------------
    distances = cfg.get("range_test", {}).get("distances_m")
    range_result = run_range_test(
        run_id,
        distances_m=distances,
        config=xbee_cfg,
        channel=cfg.get("range_test", {}).get("channel", "rf_900mhz"),
    )
    range_csv = range_result.to_csv(output_dir / "range_test.csv")

    # --- Accuracy test -------------------------------------------------
    setpoints = cfg.get("accuracy_test", {}).get("setpoints_c")
    accuracy_result = run_accuracy_test(
        run_id,
        setpoints_c=setpoints,
        config=tmp_cfg,
    )
    accuracy_csv = accuracy_result.to_csv(output_dir / "accuracy_test.csv")

    # --- BoM + energy estimate -----------------------------------------
    bom_summary = summarise_bom(DEFAULT_BOM)
    energy = energy_wh_per_event(
        active_seconds=cfg.get("energy", {}).get("active_seconds", 0.020),
        sleep_seconds=cfg.get("energy", {}).get("sleep_seconds", 9.980),
        tx_seconds=cfg.get("energy", {}).get("tx_seconds", 0.050),
        config=mcu_cfg,
    )

    # Persist CSV side-cars for BoM
    bom_csv = output_dir / "bom.csv"
    bom_csv.parent.mkdir(parents=True, exist_ok=True)
    with bom_csv.open("w", encoding="utf-8") as fh:
        fh.write("part_number,description,quantity,unit_cost_usd,total_cost_usd,weight_g,volume_cm3\n")
        for item in DEFAULT_BOM:
            fh.write(
                f"{item.part_number},{item.description},{item.quantity},"
                f"{item.unit_cost_usd:.4f},{item.total_cost_usd:.4f},"
                f"{item.weight_g},{item.volume_cm3}\n"
            )

    summary = {
        "run_id": run_id,
        "source": args.source,
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
        "firmware_version": args.firmware_version,
        "operator": args.operator,
        "range_test": {
            "samples": len(range_result.samples),
            "max_range_m_lt_50pct_per": range_result.max_range_m,
            "csv": str(range_csv),
        },
        "accuracy_test": {
            "samples": len(accuracy_result.samples),
            "max_abs_error_c": accuracy_result.max_abs_error_c,
            "mean_abs_error_c": accuracy_result.mean_abs_error_c,
            "csv": str(accuracy_csv),
        },
        "bom": bom_summary,
        "energy": energy,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # --- Persist everything into SQLite --------------------------------
    with connect(args.database) as con:
        _ensure_schema(con)
        _register_hardware_run(
            con,
            run_id=run_id,
            source=args.source,
            firmware=args.firmware_version,
            operator=args.operator,
            started_at=started_at,
            notes=f"campaign via run_hardware_demo ({args.source})",
        )
        n_range = persist_range_test(range_result, connection=con)
        n_accuracy = persist_accuracy_test(accuracy_result, connection=con)
        n_bom = persist_bom_to_db(run_id, DEFAULT_BOM, connection=con)
        _finalize_hardware_run(con, run_id, summary["ended_at"])
        con.commit()

    LOGGER.info(
        "Wrote %d range rows, %d accuracy rows, %d BoM rows into %s.",
        n_range,
        n_accuracy,
        n_bom,
        args.database,
    )

    # Tiny console banner — the verify_hardware_phase script greps this.
    print("HARDWARE_KPI_BLOCK")
    print(f"  run_id           : {run_id}")
    print(f"  source           : {args.source}")
    print(f"  range_m_max      : {range_result.max_range_m:.1f}")
    print(f"  accuracy_pm_c    : {accuracy_result.max_abs_error_c:.3f}")
    print(f"  mean_error_c     : {accuracy_result.mean_abs_error_c:.3f}")
    print(f"  bom_cost_usd     : {bom_summary['total_cost_usd']:.2f}")
    print(f"  weight_g         : {bom_summary['total_weight_g']:.1f}")
    print(f"  volume_cm3       : {bom_summary['total_volume_cm3']:.1f}")
    print(f"  energy_wh_event  : {energy['total_wh']*1000:.4f}")
    print(f"  battery_drain_pct: {energy['drain_pct']:.4f}")
    print(f"  output_dir       : {output_dir}")
    print("HARDWARE_KPI_END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
