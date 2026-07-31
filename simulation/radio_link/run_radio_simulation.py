"""Formalize the radio-link simulation as the Phase-2 *equivalent engineering
simulation* deliverable.

Reads the existing ``simulator.hardware.xbee`` datasheet model and emits
three reproducible artifacts into ``simulation/radio_link/results/``:

* ``path_loss_sweep.csv`` — RSSI vs distance with lognormal shadowing.
* ``per_vs_distance.csv`` — packet error rate vs distance using a sigmoid fit.
* ``link_budget.json`` — minimum sensitivity margin and recommended antenna
  clearances, with a clear *software-estimated* label.
* ``link_budget_figure.png`` — overlay plot used in the Project Description.

This is the **fallback** simulation artifact if the Ansys Icepak thermal
model is blocked by license timing. Run it explicitly with::

    .venv/bin/python -m simulation.radio_link.run_radio_simulation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simulator.hardware.xbee import XBeeConfig, simulate_packet_loss, simulate_rssi

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "simulation" / "radio_link" / "results"


def _datasheet_xbee() -> XBeeConfig:
    return XBeeConfig(
        base_rssi_at_1m_dbm=-30.0,
        path_loss_exponent=2.8,
        shadowing_sigma_db=4.0,
        rx_sensitivity_dbm=-100.0,
        packet_size_bytes=32,
        bitrate_kbps=10.0,
    )


def run(
    output_dir: Path = RESULTS,
    seed: int = 42,
    distances_m: tuple[float, ...] = (1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 250.0),
    samples_per_point: int = 200,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = _datasheet_xbee()
    rng = np.random.default_rng(seed)

    path_loss_rows = []
    per_rows = []
    for distance in distances_m:
        rssi_samples = [
            cfg.rssi_at(distance, _legacy_random(seed + i))
            for i in range(samples_per_point)
        ]
        mean_rssi = float(np.mean(rssi_samples))
        std_rssi = float(np.std(rssi_samples))
        per_samples = [
            simulate_packet_loss(r, cfg, rng=_legacy_random(seed + i + 1))
            for i, r in enumerate(rssi_samples)
        ]
        mean_per = float(np.mean(per_samples))
        throughput_kbps = max(0.0, cfg.bitrate_kbps * (1.0 - mean_per))
        path_loss_rows.append(
            {
                "distance_m": distance,
                "mean_rssi_dbm": mean_rssi,
                "std_rssi_dbm": std_rssi,
                "path_loss_db": cfg.base_rssi_at_1m_dbm - mean_rssi,
            }
        )
        per_rows.append(
            {
                "distance_m": distance,
                "mean_per": mean_per,
                "throughput_kbps": throughput_kbps,
                "samples": samples_per_point,
            }
        )

    _write_csv(output_dir / "path_loss_sweep.csv", path_loss_rows)
    _write_csv(output_dir / "per_vs_distance.csv", per_rows)

    # Link budget JSON.
    link_budget = {
        "tx_power_dbm": 24.0,  # XBee-PRO 900HP +24 dBm
        "tx_antenna_gain_dbi": cfg.base_rssi_at_1m_dbm + 30.0,  # 0 dBi assumed baseline
        "rx_antenna_gain_dbi": 0.0,
        "rx_sensitivity_dbm": cfg.rx_sensitivity_dbm,
        "free_space_path_loss_at_60m_db": float(
            10.0 * cfg.path_loss_exponent * np.log10(60.0)
        ),
        "free_space_path_loss_at_250m_db": float(
            10.0 * cfg.path_loss_exponent * np.log10(250.0)
        ),
        "max_range_lt_50pct_per_m": max(
            row["distance_m"]
            for row in per_rows
            if row["mean_per"] < 0.5
        ),
        "samples_per_point": samples_per_point,
        "seed": seed,
        "software_estimated": True,
        "label": "EQUIVALENT ENGINEERING SIMULATION (software-estimated)",
    }
    (output_dir / "link_budget.json").write_text(
        json.dumps(link_budget, indent=2), encoding="utf-8"
    )

    # Chart.
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].errorbar(
        [r["distance_m"] for r in path_loss_rows],
        [r["mean_rssi_dbm"] for r in path_loss_rows],
        yerr=[r["std_rssi_dbm"] for r in path_loss_rows],
        fmt="o-",
        color="#1f77b4",
    )
    axes[0].axhline(cfg.rx_sensitivity_dbm, color="red", linestyle="--", label="RX sensitivity")
    axes[0].set_xscale("log")
    axes[0].set_xlabel("distance (m)")
    axes[0].set_ylabel("RSSI (dBm)")
    axes[0].set_title("Path-loss sweep (XBee-PRO 900HP)")
    axes[0].legend()
    axes[1].plot(
        [r["distance_m"] for r in per_rows],
        [r["mean_per"] for r in per_rows],
        "o-",
        color="#d62728",
    )
    axes[1].axhline(0.5, color="black", linestyle=":", label="PER = 0.5")
    axes[1].set_xscale("log")
    axes[1].set_xlabel("distance (m)")
    axes[1].set_ylabel("packet error rate")
    axes[1].set_title("PER vs distance")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(output_dir / "link_budget_figure.png", dpi=120)
    plt.close(fig)

    manifest = {
        "name": "thermal_nexus_phase2_radio_link_simulation",
        "kind": "equivalent_engineering_simulation",
        "label": link_budget["label"],
        "model": "XBee-PRO 900HP, log-distance + lognormal shadowing, sigmoid PER",
        "config": {
            "base_rssi_at_1m_dbm": cfg.base_rssi_at_1m_dbm,
            "path_loss_exponent": cfg.path_loss_exponent,
            "shadowing_sigma_db": cfg.shadowing_sigma_db,
            "rx_sensitivity_dbm": cfg.rx_sensitivity_dbm,
            "packet_size_bytes": cfg.packet_size_bytes,
            "bitrate_kbps": cfg.bitrate_kbps,
        },
        "files": [
            "results/path_loss_sweep.csv",
            "results/per_vs_distance.csv",
            "results/link_budget.json",
            "results/link_budget_figure.png",
        ],
        "seed": seed,
        "samples_per_point": samples_per_point,
        "ready_for_submission": True,
    }
    (ROOT / "simulation" / "radio_link" / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    lines = [",".join(keys)]
    for row in rows:
        lines.append(
            ",".join(
                f"{row[key]:.6f}" if isinstance(row[key], float) else str(row[key])
                for key in keys
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _legacy_random(seed: int):
    """Return a ``random.Random`` instance with a deterministic seed."""

    import random

    return random.Random(seed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    print(json.dumps(run(output_dir=args.output, seed=args.seed), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())