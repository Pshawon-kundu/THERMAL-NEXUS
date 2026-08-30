"""Paths for the temperature-only V1 dataset."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = ROOT / "ml" / "data" / "temp_v1"
RAW_DIR = BASE_DIR / "raw"
CANONICAL_DIR = BASE_DIR / "canonical"
PROCESSED_DIR = BASE_DIR / "processed"
MODEL_READY_DIR = BASE_DIR / "model_ready"
SPLITS_DIR = BASE_DIR / "splits"
REGISTRY_DIR = BASE_DIR / "registry"

for _directory in (
    RAW_DIR,
    CANONICAL_DIR,
    PROCESSED_DIR,
    MODEL_READY_DIR,
    SPLITS_DIR,
    REGISTRY_DIR,
):
    _directory.mkdir(parents=True, exist_ok=True)
