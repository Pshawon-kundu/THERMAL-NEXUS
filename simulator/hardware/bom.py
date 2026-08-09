"""Bill of materials model + persistence.

A small typed container for each line item, plus a helper that inserts the
whole BOM into the ``bom_items`` table. Pricing is taken from a published
representative figure for each part; swap in vendor quotes when procurement
is finalised.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from host.database.connection import connect


@dataclass(frozen=True)
class BOMItem:
    """One bill-of-materials line item."""

    part_number: str
    description: str
    quantity: int
    unit_cost_usd: float
    weight_g: float
    volume_cm3: float

    @property
    def total_cost_usd(self) -> float:
        return self.unit_cost_usd * self.quantity


# Default BoM for a single sensor node. Pricing is intentionally conservative
# (single-unit, no volume discount) so the headline KPI reflects the worst
# case for procurement.
DEFAULT_BOM: tuple[BOMItem, ...] = (
    BOMItem(
        part_number="TMP117AIDRVR",
        description="TMP117 ±0.1 °C I²C temperature sensor (TI)",
        quantity=1,
        unit_cost_usd=4.10,
        weight_g=0.2,
        volume_cm3=0.5,
    ),
    BOMItem(
        part_number="STM32U585VIT6",
        description="STM32U585 Cortex-M33 ultra-low-power MCU",
        quantity=1,
        unit_cost_usd=8.20,
        weight_g=0.5,
        volume_cm3=1.5,
    ),
    BOMItem(
        part_number="XBEE-PRO-900HP",
        description="Digi XBee-PRO 900HP, +24 dBm, 900 MHz",
        quantity=1,
        unit_cost_usd=42.00,
        weight_g=4.0,
        volume_cm3=18.0,
    ),
    BOMItem(
        part_number="LIPO-1000MAH-37V",
        description="LiPo battery, 1000 mAh @ 3.7 V",
        quantity=1,
        unit_cost_usd=5.40,
        weight_g=22.0,
        volume_cm3=12.0,
    ),
    BOMItem(
        part_number="ANT-900MHZ-2DBI",
        description="900 MHz whip antenna, 2 dBi",
        quantity=1,
        unit_cost_usd=3.50,
        weight_g=2.0,
        volume_cm3=4.0,
    ),
    BOMItem(
        part_number="ENCL-IP65-ABS",
        description="ABS IP65 enclosure, 60×40×20 mm",
        quantity=1,
        unit_cost_usd=2.80,
        weight_g=18.0,
        volume_cm3=48.0,
    ),
    BOMItem(
        part_number="PCB-4LAYER-50X40",
        description="4-layer PCB, 50×40 mm",
        quantity=1,
        unit_cost_usd=2.50,
        weight_g=6.0,
        volume_cm3=8.0,
    ),
)


def summarise_bom(items: tuple[BOMItem, ...]) -> dict[str, float]:
    """Return roll-up totals for the dashboard KPI cards."""

    total_cost = sum(item.total_cost_usd for item in items)
    total_weight = sum(item.weight_g * item.quantity for item in items)
    total_volume = sum(item.volume_cm3 * item.quantity for item in items)
    return {
        "total_cost_usd": total_cost,
        "total_weight_g": total_weight,
        "total_volume_cm3": total_volume,
        "line_items": float(len(items)),
    }


def persist_bom_to_db(
    run_id: str,
    items: tuple[BOMItem, ...],
    database_path: Path | None = None,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Insert every BoM line into ``bom_items`` for the given ``run_id``.

    Pass either ``database_path`` (opens its own connection) or an open
    ``connection`` (use this when batching multiple inserts under one tx).
    """

    if connection is None and database_path is None:
        raise ValueError("persist_bom_to_db requires database_path or connection")
    own_connection = connection is None
    con = connection or connect(database_path)
    try:
        rows = 0
        for item in items:
            con.execute(
                """
                INSERT INTO bom_items (
                    part_number, run_id, description, quantity,
                    unit_cost_usd, total_cost_usd, weight_g, volume_cm3
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.part_number,
                    run_id,
                    item.description,
                    item.quantity,
                    item.unit_cost_usd,
                    item.total_cost_usd,
                    item.weight_g,
                    item.volume_cm3,
                ),
            )
            rows += 1
        if own_connection:
            con.commit()
        return rows
    finally:
        if own_connection:
            con.close()
