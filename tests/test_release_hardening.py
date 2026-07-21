"""Tests for release hardening, real-data ingestion, and integration contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.release_hardening import (
    SIMULATED_NOTICE,
    build_manifest,
    create_competition_evidence_package,
    create_final_demo_summary,
    create_release_candidate,
    validate_release_artifacts,
)
from host.ingestion.checksums import sha256_file
from host.ingestion.import_real_temperature_data import import_real_temperature_data
from host.ingestion.real_data_schema import (
    RealDataValidationError,
    validate_real_temperature_frame,
)
from ml.preprocessing.create_real_data_labels import (
    RealLabelConfig,
    create_real_data_labels,
)


def test_real_data_schema_accepts_ordered_valid_tmp117_rows() -> None:
    frame = _real_frame()
    validated = validate_real_temperature_frame(frame)
    assert len(validated) == 4
    assert validated["sensor_valid"].tolist() == [True, True, False, True]


def test_real_data_schema_rejects_bad_contract_values() -> None:
    missing = _real_frame().drop(columns=["calibration_version"])
    with pytest.raises(RealDataValidationError, match="Missing real-data columns"):
        validate_real_temperature_frame(missing)

    unordered = _real_frame()
    unordered.loc[2, "timestamp"] = "2026-01-01T00:00:30Z"
    with pytest.raises(RealDataValidationError, match="timestamps must be ordered"):
        validate_real_temperature_frame(unordered)

    nonfinite = _real_frame()
    nonfinite.loc[0, "measured_temperature"] = float("inf")
    with pytest.raises(RealDataValidationError, match="finite"):
        validate_real_temperature_frame(nonfinite)

    bad_battery = _real_frame()
    bad_battery["battery_percentage"] = [101, 99, 98, 97]
    with pytest.raises(RealDataValidationError, match="Battery percentage"):
        validate_real_temperature_frame(bad_battery)


def test_real_data_import_preserves_raw_file_and_checksum(tmp_path: Path) -> None:
    source = tmp_path / "real.csv"
    _real_frame().to_csv(source, index=False)
    report = import_real_temperature_data(source, tmp_path / "real_data")
    preserved = Path(report["preserved_raw_path"])
    assert preserved.exists()
    assert report["raw_sha256"] == sha256_file(source)
    assert sha256_file(preserved) == sha256_file(source)
    assert report["true_temperature_generated"] is False
    assert report["labels_generated"] is False


def test_real_data_labels_do_not_invent_truth_or_end_labels() -> None:
    labeled = create_real_data_labels(
        _real_frame(),
        RealLabelConfig(
            lower_limit_c=2.0,
            upper_limit_c=8.0,
            prediction_horizons_minutes=[1, 2],
        ),
    )
    assert "true_temperature" not in labeled.columns
    assert labeled["label_available_2m"].tolist()[-1] is False
    assert labeled["will_excursion_1m"].tolist()[0] is False


def test_hardware_interface_templates_exist_and_are_software_only() -> None:
    required = [
        "embedded/interfaces/temperature_source.h",
        "embedded/interfaces/clock_source.h",
        "embedded/interfaces/battery_source.h",
        "embedded/interfaces/radio_transport.h",
        "embedded/interfaces/storage_backend.h",
        "embedded/interfaces/diagnostic_logger.h",
        "embedded/stm32_integration/app_runtime.c",
        "embedded/xbee_integration/xbee_transport_contract.h",
    ]
    for relative in required:
        assert Path(relative).exists(), relative
    assert "TODO" in Path("embedded/stm32_integration/app_runtime.c").read_text(
        encoding="utf-8"
    )


def test_release_manifest_contains_versions_and_checksums() -> None:
    manifest = build_manifest()
    assert manifest["software_version"] == "software_rc1"
    assert manifest["policy_version"] == "runtime_policy_rc1"
    assert manifest["protocol_version"] == 1
    assert manifest["database_schema_version"] == 1
    assert manifest["selected_model_checksum"]
    assert manifest["feature_schema_checksum"]
    assert manifest["configuration_checksums"]
    assert manifest["limitations_notice"] == SIMULATED_NOTICE


def test_release_outputs_evidence_package_and_validation(tmp_path: Path) -> None:
    release_dir = tmp_path / "software_rc1"
    evidence_dir = tmp_path / "competition"
    demo_dir = tmp_path / "demo"
    create_release_candidate(release_dir)
    create_competition_evidence_package(evidence_dir)
    create_final_demo_summary(demo_dir)
    assert (release_dir / "RELEASE_MANIFEST.json").exists()
    assert (release_dir / "CHECKSUMS.sha256").exists()
    assert (evidence_dir / "INDEX.md").exists()
    assert (demo_dir / "DEMO_SUMMARY.md").exists()
    manifest = json.loads((release_dir / "RELEASE_MANIFEST.json").read_text())
    assert manifest["hardware_claims"] == "none"

    assert validate_release_artifacts(release_dir)["status"] == "ok"


def test_dashboard_config_uses_light_mode_and_thermal_nexus_team() -> None:
    config = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    dashboard = Path("config/dashboard.yaml").read_text(encoding="utf-8")
    assert 'base = "light"' in config
    assert "gatherUsageStats = false" in config
    assert "team_name: Thermal Nexus" in dashboard


def _real_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:01:00Z",
                "2026-01-01T00:02:00Z",
                "2026-01-01T00:03:00Z",
            ],
            "node_id": ["node-a"] * 4,
            "measured_temperature": [4.0, 4.2, None, 4.6],
            "sensor_valid": [True, True, False, True],
            "source_device": ["TMP117-bench"] * 4,
            "experiment_id": ["real-demo-001"] * 4,
            "calibration_version": ["cal-001"] * 4,
            "notes": ["bench import fixture"] * 4,
        }
    )
