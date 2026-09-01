"""Locked final test evaluation for the selected Thermal Nexus model."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import joblib
import pandas as pd

from ml.evaluation.model_metrics import evaluate_model_predictions, measure_latency_ms
from ml.training.data_loader import load_split
from ml.training.training_schema import load_training_schema

LOGGER = logging.getLogger(__name__)


class FinalTestLockError(ValueError):
    """Raised when final test evaluation is attempted without confirmation."""


def evaluate_final_model(
    model_dir: Path,
    test_path: Path,
    confirm_test_evaluation: bool,
    config_path: Path = Path("config/models.yaml"),
) -> dict[str, object]:
    """Evaluate the frozen selected model on test.csv only when confirmed."""

    if not confirm_test_evaluation:
        raise FinalTestLockError(
            "Final test evaluation is locked. Re-run with --confirm-test-evaluation."
        )
    artifact_dir = _resolve_model_dir(model_dir)
    test_frame = pd.read_csv(test_path)
    schema = load_training_schema(config_path, test_frame)
    split = load_split(test_path, schema)
    pipeline = joblib.load(artifact_dir / "pipeline.joblib")
    predictions = pd.Series(pipeline.predict(split.features))
    probabilities = (
        pipeline.predict_proba(split.features)
        if hasattr(pipeline, "predict_proba")
        else None
    )
    metrics = evaluate_model_predictions(split.frame, predictions, probabilities)
    metrics.update(measure_latency_ms(pipeline, split.features))
    metrics["model_dir"] = str(artifact_dir)
    metrics["test_evaluation_confirmed"] = True
    output = Path("evidence/models/final_test_metrics.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def _resolve_model_dir(model_dir: Path) -> Path:
    latest = model_dir / "latest_selected.json"
    if latest.exists():
        payload = json.loads(latest.read_text(encoding="utf-8"))
        return Path(payload["artifact_dir"])
    return model_dir


def main(argv: list[str] | None = None) -> int:
    """Run locked final test evaluation."""

    parser = argparse.ArgumentParser(
        description="Evaluate selected model on locked test split."
    )
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    parser.add_argument("--confirm-test-evaluation", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        metrics = evaluate_final_model(
            args.model, args.test, args.confirm_test_evaluation
        )
    except FinalTestLockError as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Final test evaluation complete: macro_f1=%.4f", metrics["macro_f1"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
