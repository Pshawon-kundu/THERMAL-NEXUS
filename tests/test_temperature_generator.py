"""Tests for synthetic temperature generation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from simulator.temperature.config import ConfigurationError, load_config
from simulator.temperature.generate import run_generation
from simulator.temperature.generator import REQUIRED_COLUMNS, build_temperature_frame

CONFIG_PATH = Path("config/scenarios.yaml")
PROJECT_CONFIG_PATH = Path("config/project.yaml")


def _scenario(name: str) -> dict[str, object]:
    config = load_config(CONFIG_PATH)
    return config.defaults | config.scenarios[name]


def test_project_configuration_contains_required_values() -> None:
    project = yaml.safe_load(PROJECT_CONFIG_PATH.read_text(encoding="utf-8"))
    values = project["project"]
    assert isinstance(values["random_seed"], int)
    assert values["default_sample_interval_seconds"] > 0
    assert values["default_experiment_duration_seconds"] > 0
    assert values["lower_temperature_limit_c"] < values["upper_temperature_limit_c"]
    assert values["prediction_horizons_minutes"] == [5, 10, 15]
    assert "synthetic_data" in values["output_directories"]


def test_deterministic_output_with_same_seed() -> None:
    config = _scenario("gradual_warming")
    frame_a = build_temperature_frame(
        "gradual_warming",
        config,
        seed=123,
        run_id="fixed-run",
        rng=np.random.default_rng(123),
    )
    frame_b = build_temperature_frame(
        "gradual_warming",
        config,
        seed=123,
        run_id="fixed-run",
        rng=np.random.default_rng(123),
    )
    pd.testing.assert_frame_equal(frame_a, frame_b)


def test_different_output_with_different_seeds() -> None:
    config = _scenario("gradual_warming")
    frame_a = build_temperature_frame(
        "gradual_warming",
        config,
        seed=123,
        run_id="run-a",
        rng=np.random.default_rng(123),
    )
    frame_b = build_temperature_frame(
        "gradual_warming",
        config,
        seed=456,
        run_id="run-b",
        rng=np.random.default_rng(456),
    )
    assert not frame_a["measured_temperature"].equals(frame_b["measured_temperature"])


def test_unique_run_ids(tmp_path: Path) -> None:
    artifacts = run_generation(CONFIG_PATH, "stable_cold", False, 3, tmp_path)
    run_ids = [artifact.run_id for artifact in artifacts]
    assert len(run_ids) == len(set(run_ids))


def test_required_columns() -> None:
    frame = build_temperature_frame(
        "stable_cold",
        _scenario("stable_cold"),
        seed=123,
        run_id="fixed-run",
        rng=np.random.default_rng(123),
    )
    assert list(frame.columns) == REQUIRED_COLUMNS


def test_gradual_warming_general_trend_is_monotonic() -> None:
    frame = build_temperature_frame(
        "gradual_warming",
        _scenario("gradual_warming"),
        seed=123,
        run_id="fixed-run",
        rng=np.random.default_rng(123),
    )
    assert frame["true_temperature"].is_monotonic_increasing
    assert frame["true_temperature"].iloc[-1] > frame["true_temperature"].iloc[0]


def test_transition_direction() -> None:
    cold_to_ambient = build_temperature_frame(
        "cold_to_ambient",
        _scenario("cold_to_ambient"),
        seed=123,
        run_id="warm",
        rng=np.random.default_rng(123),
    )
    ambient_to_cold = build_temperature_frame(
        "ambient_to_cold",
        _scenario("ambient_to_cold"),
        seed=123,
        run_id="cool",
        rng=np.random.default_rng(123),
    )
    assert (
        cold_to_ambient["true_temperature"].iloc[-1]
        > cold_to_ambient["true_temperature"].iloc[0]
    )
    assert (
        ambient_to_cold["true_temperature"].iloc[-1]
        < ambient_to_cold["true_temperature"].iloc[0]
    )


def test_missing_sample_generation() -> None:
    frame = build_temperature_frame(
        "missing_samples",
        _scenario("missing_samples"),
        seed=123,
        run_id="fixed-run",
        rng=np.random.default_rng(123),
    )
    assert (~frame["sensor_valid"]).any()
    assert frame.loc[~frame["sensor_valid"], "measured_temperature"].isna().all()


def test_invalid_sensor_state_generation() -> None:
    frame = build_temperature_frame(
        "temporary_sensor_fault",
        _scenario("temporary_sensor_fault"),
        seed=123,
        run_id="fixed-run",
        rng=np.random.default_rng(123),
    )
    assert (~frame["sensor_valid"]).any()


def test_valid_csv_metadata_and_plot_creation(tmp_path: Path) -> None:
    artifact = run_generation(CONFIG_PATH, "gradual_warming", False, 1, tmp_path)[0]
    assert artifact.csv_path.exists()
    assert artifact.metadata_path.exists()
    assert artifact.plot_path.exists()
    assert artifact.csv_path.stat().st_size > 0
    assert artifact.plot_path.stat().st_size > 0

    frame = pd.read_csv(artifact.csv_path)
    assert list(frame.columns) == REQUIRED_COLUMNS

    metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
    assert metadata["run_id"] == artifact.run_id
    assert metadata["scenario"] == "gradual_warming"
    assert "Synthetic software-only data" in metadata["disclaimer"]


def test_invalid_configuration_handling(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text(
        """
defaults:
  random_seed: 1
  sample_interval_seconds: 0
  duration_seconds: 60
  lower_limit_c: 8
  upper_limit_c: 2
  initial_temperature_c: 4
  sensor_noise_std_c: 0.1
  output_dir: out
scenarios:
  bad:
    type: stable
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError):
        load_config(bad_config)
