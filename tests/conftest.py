"""Shared pytest fixtures and skip configuration.

This conftest enforces two isolation rules:

1. **External T15 tests** (``pytestmark = external_t15``) are skipped on a
   clean clone when the raw ``NEW-DATA-*.T15.txt`` files are not present
   under ``ml/data/external/t15/raw/``. Re-enable explicitly by passing
   ``--runs-external-t15`` on the command line (the option is wired into
   ``tools/run_tests.ps1`` already) or by restoring the raw data.

2. **Hardware tests** (marked ``hardware``) are skipped unless
   ``--runs-hardware`` is passed. The hardware demonstrator is generated
   on demand; the CI suite does not depend on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
T15_RAW_DIR = ROOT / "ml" / "data" / "external" / "t15" / "raw"
T15_REQUIRED_FILES = ("NEW-DATA-1.T15.txt", "NEW-DATA-2.T15.txt")


def _t15_raw_available() -> bool:
    return all((T15_RAW_DIR / name).exists() for name in T15_REQUIRED_FILES)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("thermal-nexus")
    group.addoption(
        "--runs-external-t15",
        action="store_true",
        default=False,
        help="Run external T15 dataset tests (require raw data on disk).",
    )
    group.addoption(
        "--runs-hardware",
        action="store_true",
        default=False,
        help="Run hardware demonstrator tests (require firmware/ and evidence/).",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip T15 tests on clean clone and hardware tests unless explicitly opted in."""

    runs_external_t15 = bool(config.getoption("--runs-external-t15"))
    runs_hardware = bool(config.getoption("--runs-hardware"))

    skip_external_t15 = pytest.mark.skip(
        reason=(
            "External T15 raw data not present on disk. "
            "Pass --runs-external-t15 or unpack NEW-DATA-*.T15.txt into "
            "ml/data/external/t15/raw/ to enable these tests."
        )
    )
    skip_hardware = pytest.mark.skip(
        reason=(
            "Hardware demonstrator not built. Pass --runs-hardware once the "
            "Phase 2 firmware/hardware is in evidence/."
        )
    )

    raw_available = _t15_raw_available()

    for item in items:
        if "external_t15" in item.keywords:
            if not (runs_external_t15 or raw_available):
                item.add_marker(skip_external_t15)
        if "hardware" in item.keywords:
            if not runs_hardware:
                item.add_marker(skip_hardware)
