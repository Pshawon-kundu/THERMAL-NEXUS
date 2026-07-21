"""Import future real TMP117 temperature CSV files without fabricating labels."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from host.ingestion.checksums import sha256_file
from host.ingestion.real_data_schema import (
    RealDataValidationError,
    validate_real_temperature_frame,
)


def import_real_temperature_data(
    input_csv: Path,
    output_dir: Path = Path("evidence/real_data"),
) -> dict[str, object]:
    """Validate and preserve raw physical-data CSV evidence unchanged."""

    if not input_csv.exists():
        raise RealDataValidationError(f"Real-data file not found: {input_csv}")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_checksum = sha256_file(input_csv)
    frame = pd.read_csv(input_csv)
    validated = validate_real_temperature_frame(frame)
    experiment_id = str(validated["experiment_id"].iloc[0])
    preserved = output_dir / f"{experiment_id}_raw.csv"
    if not preserved.exists():
        shutil.copy2(input_csv, preserved)
    report = {
        "status": "pass",
        "imported_at": datetime.now(UTC).isoformat(),
        "source_path": str(input_csv),
        "preserved_raw_path": str(preserved),
        "raw_sha256": raw_checksum,
        "row_count": int(len(validated)),
        "experiment_id": experiment_id,
        "source_device": str(validated["source_device"].iloc[0]),
        "calibration_version": str(validated["calibration_version"].iloc[0]),
        "true_temperature_generated": False,
        "labels_generated": False,
        "notes": "Real data imported without invented ground truth or labels.",
    }
    (output_dir / f"{experiment_id}_import_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("evidence/real_data"))
    args = parser.parse_args()
    print(json.dumps(import_real_temperature_data(args.input, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
