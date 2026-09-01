"""Phase-2 submission verification tests.

These tests are the gating criteria for the IEEE HART HardwAIre Challenge
Phase-2 submission. They check that the supporting evidence files exist
and that the embedded C99 model compiles into a real (non-stub) artefact.

The Phase-2 portal requires the following mandatory artefacts by 10
September 2026:

* a 2-page Project Description PDF (or markdown that fits 2 pages when
  rendered);
* a 5-minute-or-less Video Presentation file;
* a Simulations File (Ansys source or equivalent engineering simulation);
* a Cost and Measurements artefact (BoM, energy, size/weight, range,
  accuracy).

The tests are deliberately tolerant of partial completion so they can
guide progress without blocking other work. They raise actionable
``AssertionError`` messages that point to the missing artefact.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _exists(rel: str) -> Path:
    return ROOT / rel


def test_embedded_c99_model_compiles() -> None:
    """The exported C99 model must compile cleanly with strict warnings."""

    compiler = shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("No C compiler available.")
    src = _exists("embedded/generated/thermal_nexus_model.c")
    if not src.exists():
        pytest.skip("Run `python -m embedded.deployment.export_model` first.")
    cmd = [
        compiler,
        "-std=c99",
        "-Wall",
        "-Wextra",
        "-c",
        str(src),
        "-o",
        "/tmp/thermal_nexus_phase2.o",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, (
        f"C99 model failed to compile: {result.stderr}"
    )


def test_golden_vectors_compile_under_c99() -> None:
    """The golden-vector header must produce a valid C99 translation unit."""

    compiler = shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("No C compiler available.")
    header = _exists("embedded/golden_vectors/golden_vectors.h")
    if not header.exists():
        pytest.skip("Run `python -m embedded.deployment.generate_golden_vectors` first.")
    driver = _exists("embedded/tests/parity_runner.c")
    cmd = [
        compiler,
        "-std=c99",
        "-Wall",
        "-Wextra",
        "-I",
        str(_exists("embedded/generated")),
        "-I",
        str(_exists("embedded/golden_vectors")),
        str(driver),
        str(_exists("embedded/generated/thermal_nexus_model.c")),
        "-o",
        "/tmp/thermal_nexus_phase2_runner",
        "-lm",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, (
        "Golden vectors did not compile cleanly. The generator emitted an "
        f"invalid C99 float literal: {result.stderr}"
    )


def test_radio_link_simulation_artifact_present() -> None:
    """Either Ansys Icepak or the equivalent radio-link simulation must exist."""

    radio_manifest = _exists("simulation/radio_link/manifest.json")
    ansys_manifest = _exists("simulation/ansys/manifest.json")
    assert (
        radio_manifest.exists() or ansys_manifest.exists()
    ), (
        "No simulation artifact found. Generate one with:\n"
        "  python -m simulation.radio_link.run_radio_simulation"
    )


def test_energy_policy_summary_present() -> None:
    """The Phase-2 energy policy report must exist (or be regenerable)."""

    summary = _exists("evidence/ai/energy_policy_summary.json")
    assert summary.exists(), (
        "Energy policy summary missing. Run:\n"
        "  python -m analysis.energy_policy_report --output evidence/ai"
    )


def test_embedded_parity_report_status() -> None:
    """The latest parity report must show ``pass`` (no uniform-stub regression)."""

    report = _exists("evidence/embedded/PARITY_REPORT.md")
    if not report.exists():
        pytest.skip("Parity report not yet generated.")
    text = report.read_text(encoding="utf-8")
    assert "Status: `pass`" in text, (
        f"Parity report is not 'pass'. Latest contents:\n{text}"
    )


@pytest.mark.parametrize(
    "deliverable_path, deliverable_name",
    [
        ("docs/project_description_2page.md", "Project Description"),
        ("docs/project_description_2page.pdf", "Project Description PDF"),
        ("docs/video_script_5min.md", "Video script"),
        ("docs/video_shot_list.md", "Video shot list"),
        ("releases/PHASE2_SUBMISSION.zip", "Submission bundle"),
    ],
)
def test_phase2_deliverable_optional(deliverable_path: str, deliverable_name: str) -> None:
    """Each Phase-2 narrative deliverable should exist; missing files warn."""

    path = _exists(deliverable_path)
    if not path.exists():
        pytest.skip(
            f"{deliverable_name} not yet written ({deliverable_path}). "
            "This is a Phase-2 deliverable; track progress via the plan file."
        )