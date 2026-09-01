"""Phase-2 embedded parity tests.

These tests enforce two Phase-2 acceptance gates the simpler embedded
tests do not:

1. The exported C99 model must be a **real** model — no uniform-probability
   stub. The regression of the LR exporter is the highest-impact Phase-2
   blocker and must be caught here.
2. The exported C99 model must match the Python pipeline within
   ``1e-4`` maximum absolute probability error across every golden vector,
   and the predicted class index must agree.

These tests compile ``embedded/tests/parity_runner.c`` and
``embedded/generated/thermal_nexus_model.c`` against the golden vectors,
then compare the per-vector probabilities against the Python pipeline.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import joblib
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "embedded" / "generated"
TESTS_DIR = ROOT / "embedded" / "tests"
GOLDEN_DIR = ROOT / "embedded" / "golden_vectors"
GOLDEN_JSON = GOLDEN_DIR / "golden_vectors.json"

PROBABILITY_TOLERANCE = 1e-4


def _compiler_or_skip() -> str:
    compiler = shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("No C compiler available for Phase 2 parity test.")
    return compiler


def _load_pipeline():
    config = yaml.safe_load(
        (ROOT / "config" / "embedded_export.yaml").read_text(encoding="utf-8")
    )
    runtime_root = ROOT / config["selected_model_path"]
    latest = runtime_root / "latest_selected.json"
    if latest.exists():
        import json

        info = json.loads(latest.read_text(encoding="utf-8"))
        artifact = (ROOT / info["artifact_dir"]).resolve()
    else:
        artifact = runtime_root
    if not (artifact / "pipeline.joblib").exists():
        pytest.skip(f"No selected pipeline at {artifact}")
    return joblib.load(artifact / "pipeline.joblib")


def test_embedded_model_is_not_a_uniform_probability_stub() -> None:
    """The C99 model must produce discriminative probabilities (no uniform stub)."""

    _compiler_or_skip()
    if not GOLDEN_JSON.exists():
        pytest.skip(f"Missing golden vectors at {GOLDEN_JSON}")
    compiler = _compiler_or_skip()
    exe = ROOT / "evidence" / "embedded" / "phase2_runner.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        compiler,
        "-std=c99",
        "-I",
        str(GENERATED_DIR),
        "-I",
        str(GOLDEN_DIR),
        str(TESTS_DIR / "parity_runner.c"),
        str(GENERATED_DIR / "thermal_nexus_model.c"),
        "-o",
        str(exe),
        "-lm",
    ]
    compile_result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if compile_result.returncode != 0:
        pytest.fail(
            f"C99 model did not compile cleanly.\n"
            f"stdout: {compile_result.stdout}\nstderr: {compile_result.stderr}"
        )
    run = subprocess.run([str(exe)], capture_output=True, text=True, check=False)
    uniform_lines = [line for line in run.stdout.splitlines() if "uniform_stub=" in line]
    if not uniform_lines:
        pytest.fail(
            "Parity runner did not emit a uniform-stub summary line. "
            "Was the latest parity_runner.c copied to TESTS_DIR?"
        )
    token = uniform_lines[0].split("uniform_stub=")[1].split()[0]
    uniform_count = int(token)
    assert uniform_count == 0, (
        f"C99 model returned uniform probabilities for {uniform_count} "
        "golden vectors. The LR exporter has regressed to the uniform stub."
    )


def test_embedded_probabilities_match_python_pipeline() -> None:
    """C99 probabilities match Python within ``1e-4`` for every vector."""

    _compiler_or_skip()
    if not GOLDEN_JSON.exists():
        pytest.skip(f"Missing golden vectors at {GOLDEN_JSON}")
    pipeline = _load_pipeline()
    import json
    import numpy as np

    raw = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))
    feature_order = list(raw[0]["raw_feature_values"].keys())
    expected_rows = []
    for vector in raw:
        row = np.array(
            [[float(vector["raw_feature_values"][k]) for k in feature_order]],
            dtype=np.float64,
        )
        expected_rows.append(pipeline.predict_proba(row)[0].tolist())

    compiler = _compiler_or_skip()
    exe = ROOT / "evidence" / "embedded" / "phase2_runner.exe"
    if not exe.exists():
        exe.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            compiler,
            "-std=c99",
            "-I",
            str(GENERATED_DIR),
            "-I",
            str(GOLDEN_DIR),
            str(TESTS_DIR / "parity_runner.c"),
            str(GENERATED_DIR / "thermal_nexus_model.c"),
            "-o",
            str(exe),
            "-lm",
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    run = subprocess.run([str(exe)], capture_output=True, text=True, check=True)

    max_diff = 0.0
    class_mismatches = 0
    for line in run.stdout.splitlines():
        if not line.startswith("vector="):
            continue
        parts = line.split()
        emitted = [float(p) for p in parts[2].split("=")[1].split(";")]
        index = int(parts[0].split("=")[1])
        expect = expected_rows[index]
        for a, b in zip(emitted, expect):
            max_diff = max(max_diff, abs(a - b))
        # Predicted class in C99 matches Python's argmax of expected.
        predicted_c = int(parts[1].split("=")[1])
        predicted_py = max(range(len(expect)), key=lambda j: expect[j])
        if predicted_c != predicted_py:
            class_mismatches += 1

    assert max_diff <= PROBABILITY_TOLERANCE, (
        f"C99 vs Python max probability diff {max_diff:.2e} exceeds "
        f"{PROBABILITY_TOLERANCE:.0e} tolerance."
    )
    assert class_mismatches == 0, (
        f"C99 predicted class disagrees with Python pipeline on "
        f"{class_mismatches} of {len(raw)} vectors."
    )
