"""Safe runtime wrapper for selected Thermal Nexus model artifacts."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ml.features.feature_schema import (
    FeatureSchemaError,
    assert_no_prohibited_columns,
    prohibited_columns,
)

STATE_BY_CODE = {0: "STABLE", 1: "TRANSITION", 2: "EXCURSION_RISK"}
CODE_BY_STATE = {value: key for key, value in STATE_BY_CODE.items()}


class ModelRuntimeError(RuntimeError):
    """Raised when runtime inference cannot safely proceed."""


@dataclass(frozen=True)
class RuntimePrediction:
    """One runtime prediction result."""

    predicted_state: str
    predicted_state_code: int
    probabilities: dict[str, float]
    latency_ms: float
    model_version: str
    checksum: str
    fallback_status: str


class ModelRuntime:
    """Load a selected sklearn artifact and run strict single-row inference."""

    def __init__(self, selected_dir: Path = Path("ml/models/selected")) -> None:
        self.selected_dir = selected_dir
        self.artifact_dir: Path | None = None
        self.pipeline: Any | None = None
        self.feature_order: list[str] = []
        self.class_mapping: dict[str, int] = {}
        self.checksums: dict[str, str] = {}
        self.model_version = "unavailable"
        self.loaded = False
        self.load_error: str | None = None
        self._load()

    def predict(self, frame: pd.DataFrame) -> RuntimePrediction:
        """Predict state for one or more rows using frozen feature ordering."""

        if not self.loaded or self.pipeline is None:
            return self._fallback(f"model unavailable: {self.load_error}")
        try:
            features = self._validate_features(frame)
            start = time.perf_counter()
            codes = self.pipeline.predict(features)
            probabilities = self._probabilities(features)
            latency_ms = (time.perf_counter() - start) * 1000.0
            state, code = self._state_and_code(codes[-1])
            return RuntimePrediction(
                predicted_state=state,
                predicted_state_code=code,
                probabilities=probabilities,
                latency_ms=latency_ms,
                model_version=self.model_version,
                checksum=self.checksums.get("pipeline.joblib", ""),
                fallback_status="ok",
            )
        except Exception as exc:
            return self._fallback(f"inference failure: {exc}")

    def _load(self) -> None:
        try:
            artifact_dir = self._resolve_artifact_dir()
            self._require_files(artifact_dir)
            feature_schema = json.loads(
                (artifact_dir / "feature_schema.json").read_text(encoding="utf-8")
            )
            self.feature_order = [str(value) for value in feature_schema["features"]]
            self.class_mapping = json.loads(
                (artifact_dir / "class_mapping.json").read_text(encoding="utf-8")
            )
            self.checksums = json.loads(
                (artifact_dir / "checksums.json").read_text(encoding="utf-8")
            )
            self._validate_checksum(artifact_dir / "pipeline.joblib")
            self.pipeline = joblib.load(artifact_dir / "pipeline.joblib")
            self.artifact_dir = artifact_dir
            self.model_version = artifact_dir.name
            self.loaded = True
        except Exception as exc:
            self.loaded = False
            self.load_error = str(exc)

    def _resolve_artifact_dir(self) -> Path:
        latest = self.selected_dir / "latest_selected.json"
        if latest.exists():
            raw = json.loads(latest.read_text(encoding="utf-8"))
            path = Path(str(raw["artifact_dir"]))
            return path if path.is_absolute() else Path.cwd() / path
        candidates = sorted(
            [path for path in self.selected_dir.iterdir() if path.is_dir()],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise ModelRuntimeError("No selected model artifact directory found.")
        return candidates[0]

    def _require_files(self, artifact_dir: Path) -> None:
        required = [
            "pipeline.joblib",
            "model.joblib",
            "preprocessing.joblib",
            "feature_schema.json",
            "class_mapping.json",
            "configuration.yaml",
            "MODEL_CARD.md",
            "checksums.json",
        ]
        missing = [name for name in required if not (artifact_dir / name).exists()]
        if missing:
            raise ModelRuntimeError("Selected artifact missing: " + ", ".join(missing))

    def _validate_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        bad = prohibited_columns(frame.columns)
        if bad:
            raise FeatureSchemaError(
                "Prohibited runtime input columns detected: " + ", ".join(bad)
            )
        missing = [column for column in self.feature_order if column not in frame]
        if missing:
            raise ModelRuntimeError("Missing runtime features: " + ", ".join(missing))
        features = frame[self.feature_order].copy()
        assert_no_prohibited_columns(features)
        numeric = features.apply(pd.to_numeric, errors="coerce")
        values = numeric.to_numpy(dtype=float)
        if np.isnan(values).any():
            raise ModelRuntimeError("Runtime features contain NaN values.")
        if not np.isfinite(values).all():
            raise ModelRuntimeError("Runtime features contain infinite values.")
        return numeric

    def _probabilities(self, features: pd.DataFrame) -> dict[str, float]:
        if self.pipeline is None or not hasattr(self.pipeline, "predict_proba"):
            return {}
        raw = self.pipeline.predict_proba(features)[-1]
        classes = list(getattr(self.pipeline, "classes_", []))
        return {
            self._state_and_code(label)[0]: float(prob)
            for label, prob in zip(classes, raw, strict=True)
        }

    def _state_for_code(self, code: int) -> str:
        inverse = {int(value): key for key, value in self.class_mapping.items()}
        return inverse.get(code, STATE_BY_CODE.get(code, "STABLE"))

    def _state_and_code(self, label: object) -> tuple[str, int]:
        if isinstance(label, str):
            state = label
            return state, int(
                self.class_mapping.get(state, CODE_BY_STATE.get(state, 0))
            )
        code = int(float(str(label)))
        return self._state_for_code(code), code

    def _fallback(self, reason: str) -> RuntimePrediction:
        return RuntimePrediction(
            predicted_state="MODEL_FAULT",
            predicted_state_code=3,
            probabilities={},
            latency_ms=0.0,
            model_version=self.model_version,
            checksum=self.checksums.get("pipeline.joblib", ""),
            fallback_status=reason,
        )

    def _validate_checksum(self, path: Path) -> None:
        expected = self.checksums.get(path.name)
        if not expected:
            raise ModelRuntimeError(f"Missing checksum for {path.name}.")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ModelRuntimeError(f"Checksum mismatch for {path.name}.")
