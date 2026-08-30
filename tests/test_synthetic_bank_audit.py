from pathlib import Path

from ml.synthetic_bank.audit import audit_bank

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_bank_inventory_and_provenance(tmp_path: Path) -> None:
    report = audit_bank(ROOT / "Datasets" / "CustomDataset" / "raw", tmp_path)
    assert report["run_count"] == 104
    assert report["scenario_count"] == 13
    assert report["sample_count"] == 12584
    assert report["valid_sample_count"] == 12246
    assert report["provenance_errors"] == []
    assert report["robustness_only_run_count"] == 24
    assert report["training_eligible_run_count"] == 72


def test_synthetic_outputs_and_checksum_manifest(tmp_path: Path) -> None:
    audit_bank(ROOT / "Datasets" / "CustomDataset" / "raw", tmp_path)
    for name in (
        "synthetic_dataset_registry.csv",
        "robustness_suite_registry.csv",
        "synthetic_checksums.csv",
        "synthetic_audit_report.json",
        "SYNTHETIC_DATASET_CARD.md",
        "SYNTHETIC_DATASET_VERSION.json",
    ):
        assert (tmp_path / name).exists()
    assert sum(1 for _ in (tmp_path / "synthetic_checksums.csv").open()) == 209


def test_robustness_is_excluded_from_normal_training(tmp_path: Path) -> None:
    audit_bank(ROOT / "Datasets" / "CustomDataset" / "raw", tmp_path)
    rows = (tmp_path / "robustness_suite_registry.csv").read_text(encoding="utf-8")
    assert ",False,True" in rows
    assert "missing_samples" in rows
