"""Mode B rule-based adaptive operation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.baselines.rule_based import load_rule_config, predict_rule_based


def predict_mode_b(
    feature_frame: pd.DataFrame,
    config_path: Path = Path("config/baselines.yaml"),
) -> tuple[str, int, dict[str, float], str]:
    """Run the existing rule-based predictor and return the newest state."""

    config = load_rule_config(config_path)
    prediction = predict_rule_based(feature_frame, config).iloc[-1]
    state = str(prediction["predicted_state"])
    code = int(prediction["predicted_state_code"])
    return state, code, {state: 1.0}, "rule-based baseline"
