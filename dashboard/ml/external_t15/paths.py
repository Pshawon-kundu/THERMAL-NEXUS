"""Path constants for the external T15 benchmark phase."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "ml" / "data" / "external" / "t15" / "processed"
MODEL_READY_DIR = ROOT / "ml" / "data" / "external" / "t15" / "model_ready"
EVIDENCE_DIR = ROOT / "evidence" / "external_t15"
SOURCE_DATASET = PROCESSED_DIR / "thermal_nexus_external_benchmark.csv"
SOURCE_MANIFEST = PROCESSED_DIR / "dataset_manifest.csv"
SOURCE_AUDIT = PROCESSED_DIR / "dataset_audit.json"
