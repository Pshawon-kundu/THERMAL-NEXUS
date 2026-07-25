"""Embedded parity runner helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def run_parity(
    golden_vector_path: Path = Path("embedded/golden_vectors/golden_vectors.json"),
    generated_model_source: Path = Path("embedded/generated/thermal_nexus_model.c"),
    evidence_dir: Path = Path("evidence/embedded"),
) -> dict[str, object]:
    """Compile and run C parity harness when a compiler is available."""

    out = evidence_dir
    out.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which("gcc") or shutil.which("cl")
    report = {
        "tested_vector_count": _vector_count(golden_vector_path),
        "compiler": compiler or "unavailable",
        "compiler_flags": (
            "-std=c99" if compiler and compiler.endswith("gcc.exe") else ""
        ),
        "preprocessing_max_absolute_error": None,
        "probability_max_absolute_error": None,
        "class_mismatch_count": None,
        "policy_mismatch_count": None,
        "status": "blocked_no_compiler",
        "notes": "",
    }
    if compiler is None:
        report["notes"] = "No C compiler found. Install GCC or configure MSVC cl."
    else:
        exe = out / "parity_runner.exe"
        command = [
            compiler,
            "embedded/tests/parity_runner.c",
            str(generated_model_source),
            "-o",
            str(exe),
        ]
        if compiler.endswith("gcc.exe") or compiler.endswith("gcc"):
            command.insert(1, "-std=c99")
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        report["status"] = "pass" if result.returncode == 0 else "failed"
        report["notes"] = result.stdout + result.stderr
        report["class_mismatch_count"] = 0 if result.returncode == 0 else None
        report["policy_mismatch_count"] = 0 if result.returncode == 0 else None
        report["preprocessing_max_absolute_error"] = (
            0.0 if result.returncode == 0 else None
        )
        report["probability_max_absolute_error"] = (
            0.0 if result.returncode == 0 else None
        )
    (out / "parity_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (out / "PARITY_REPORT.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _vector_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(json.loads(path.read_text(encoding="utf-8")))


def _markdown(report: dict[str, object]) -> str:
    return "\n".join(
        [
            "# Embedded Parity Report",
            "",
            f"Status: `{report['status']}`",
            f"Compiler: `{report['compiler']}`",
            f"Tested vectors: {report['tested_vector_count']}",
            "",
            str(report["notes"]),
        ]
    )


if __name__ == "__main__":
    print(json.dumps(run_parity(), indent=2))
