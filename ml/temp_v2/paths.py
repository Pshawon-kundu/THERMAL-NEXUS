from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "ml" / "data" / "temp_v2"
MODEL_DIR = ROOT / "ml" / "models" / "temp_v2"
EVIDENCE_DIR = ROOT / "evidence" / "temp_v2"
for directory in (DATA_DIR, MODEL_DIR, EVIDENCE_DIR):
    directory.mkdir(parents=True, exist_ok=True)
