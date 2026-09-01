"""Phase-2 submission verification script.

Runs every Phase-2 acceptance gate in one command and prints a pass/fail
table. Returns a non-zero exit code if any mandatory gate fails.

Usage::

    python -m scripts.verify_phase2            # human-readable report
    python -m scripts.verify_phase2 --strict   # also fail on optional gates
    python -m scripts.verify_phase2 --json     # machine-readable output

Gates enforced:

* Embedded C99 model compiles cleanly with strict warnings.
* Golden-vector header produces a valid translation unit.
* Embedded parity report passes (max prob error ≤ 1e-4, no stubs).
* Embedded resource estimate exists.
* Energy-policy evidence exists with at least one adaptive vs fixed
  comparison row.
* Simulation artefact exists — either Ansys manifest + at least one
  result file, or the radio-link equivalent engineering simulation.
* Test suite is green (``pytest -q``) — skipped tests allowed.
* Project Description draft is ≤ 1050 words.
* Video shot list / script drafts exist (optional gate, --strict only).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class GateResult:
    name: str
    status: str  # "pass" | "fail" | "skip"
    detail: str = ""
    mandatory: bool = True

    def as_row(self) -> str:
        marker = (
            "PASS"
            if self.status == "pass"
            else ("FAIL" if self.status == "fail" else "SKIP")
        )
        flag = " *" if self.mandatory else "  "
        return f"  [{marker}]{flag} {self.name:<48} {self.detail}"


@dataclass
class Verifier:
    gates: list[GateResult] = field(default_factory=list)

    def add(
        self,
        name: str,
        fn: Callable[[], tuple[bool, str]],
        *,
        mandatory: bool = True,
    ) -> None:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001 — surface as gate failure
            self.gates.append(
                GateResult(
                    name=name,
                    status="fail",
                    detail=f"unhandled error: {exc.__class__.__name__}: {exc}",
                    mandatory=mandatory,
                )
            )
            return
        self.gates.append(
            GateResult(
                name=name,
                status="pass" if ok else "fail",
                detail=detail,
                mandatory=mandatory,
            )
        )

    def failed(self) -> list[GateResult]:
        return [g for g in self.gates if g.status == "fail"]


# ---------------------------------------------------------------------------
# Individual gate implementations
# ---------------------------------------------------------------------------


def _exists(rel: str) -> Path:
    return ROOT / rel


def gate_embedded_c99_compiles() -> tuple[bool, str]:
    compiler = shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        return False, "no C compiler available (gcc or clang required)"
    src = _exists("embedded/generated/thermal_nexus_model.c")
    if not src.exists():
        return False, "embedded/generated/thermal_nexus_model.c missing"
    cmd = [
        compiler,
        "-std=c99",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-c",
        str(src),
        "-o",
        "/tmp/verify_phase2_model.o",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return False, f"gcc/clang returned {proc.returncode}: {proc.stderr.strip()}"
    return True, f"{Path(compiler).name} -std=c99 -Wall -Wextra -Werror"


def gate_golden_vectors_compile() -> tuple[bool, str]:
    compiler = shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        return False, "no C compiler available"
    header = _exists("embedded/golden_vectors/golden_vectors.h")
    driver = _exists("embedded/tests/parity_runner.c")
    if not header.exists() or not driver.exists():
        return False, "golden_vectors.h or parity_runner.c missing"
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
        "/tmp/verify_phase2_parity",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return False, f"compile failed: {proc.stderr.strip()[:300]}"
    return True, "parity_runner compiled"


def gate_parity_report() -> tuple[bool, str]:
    report = _exists("evidence/embedded/parity_report.json")
    if not report.exists():
        return False, "evidence/embedded/parity_report.json missing"
    data = json.loads(report.read_text(encoding="utf-8"))
    if data.get("status") != "pass":
        return False, f"status={data.get('status')!r}"
    if int(data.get("uniform_stub_count", 0)) > 0:
        return False, f"uniform stubs: {data['uniform_stub_count']}"
    prob_err = data.get("probability_max_absolute_error")
    if prob_err is None or float(prob_err) > 1e-4:
        return False, f"max prob error {prob_err} exceeds 1e-4"
    cls_mismatch = int(data.get("class_mismatch_count", 0))
    if cls_mismatch > 0:
        return False, f"class mismatches: {cls_mismatch}"
    return (
        True,
        f"max prob error {float(prob_err):.2e}, "
        f"vectors {data.get('tested_vector_count')}",
    )


def gate_resource_estimate() -> tuple[bool, str]:
    report = _exists("evidence/embedded/resource_estimate.json")
    if not report.exists():
        return False, "evidence/embedded/resource_estimate.json missing"
    data = json.loads(report.read_text(encoding="utf-8"))
    ram = int(data.get("total_static_ram_bytes", 0))
    flash = int(data.get("estimated_flash_size_bytes", 0))
    if ram <= 0 or flash <= 0:
        return False, f"ram={ram} flash={flash}"
    return True, f"ram {ram} B / flash {flash} B (estimated)"


def gate_energy_policy() -> tuple[bool, str]:
    summary = _exists("evidence/ai/energy_policy_summary.json")
    comparison = _exists("evidence/ai/energy_policy_comparison.csv")
    if not summary.exists() or not comparison.exists():
        return False, "energy_policy_summary.json or comparison.csv missing"
    data = json.loads(summary.read_text(encoding="utf-8"))
    by_mode = data.get("by_mode", {})
    if "fixed" not in by_mode or "ml" not in by_mode:
        return False, "by_mode must contain fixed and ml"
    return True, (
        f"ml={by_mode['ml']['total_transmissions']} pkts, "
        f"fixed={by_mode['fixed']['total_transmissions']} pkts"
    )


def gate_simulation_artifact() -> tuple[bool, str]:
    """Either Ansys manifest + result OR radio-link equivalent simulation."""

    ansys_manifest = _exists("simulation/ansys/manifest.json")
    radio_manifest = _exists("simulation/radio_link/manifest.json")
    radio_link_budget = _exists("simulation/radio_link/results/link_budget.json")
    radio_per = _exists("simulation/radio_link/results/per_vs_distance.csv")
    radio_path_loss = _exists("simulation/radio_link/results/path_loss_sweep.csv")
    radio_figure = _exists("simulation/radio_link/results/link_budget_figure.png")
    if ansys_manifest.exists() and any(
        _exists(f"simulation/ansys/results/{name}").exists()
        for name in ("sensor_temperature.csv", "mesh_sensitivity.csv")
    ):
        return True, "Ansys manifest + result file present"
    if all(
        p.exists()
        for p in (
            radio_manifest,
            radio_link_budget,
            radio_per,
            radio_path_loss,
            radio_figure,
        )
    ):
        return True, "radio-link equivalent engineering simulation present"
    return False, (
        "need simulation/ansys/manifest.json + a result file, "
        "or simulation/radio_link/* (manifest, link_budget, csvs, figure)"
    )


def gate_test_suite() -> tuple[bool, str]:
    """Run pytest -q; allow external_t15 + integration skips."""

    pytest_bin = _exists(".venv/bin/python")
    if not pytest_bin.exists():
        return False, ".venv/bin/python not found; venv missing"
    proc = subprocess.run(
        [str(pytest_bin), "-m", "pytest", "-q", "--tb=no"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    if proc.returncode != 0:
        return False, f"pytest failed: {summary or proc.stderr.strip()[:200]}"
    return True, summary or "all tests passed"


def gate_project_description_word_count(max_words: int = 1050) -> tuple[bool, str]:
    path = _exists("docs/project_description_2page.md")
    if not path.exists():
        return False, "docs/project_description_2page.md missing"
    text = path.read_text(encoding="utf-8")
    word_count = len(text.split())
    if word_count > max_words:
        return False, f"{word_count} words exceeds limit {max_words}"
    return True, f"{word_count} words (≤ {max_words})"


def gate_video_script_draft() -> tuple[bool, str]:
    script = _exists("docs/video_script_5min.md")
    shot_list = _exists("docs/video_shot_list.md")
    if not script.exists() or not shot_list.exists():
        return False, "video_script_5min.md or video_shot_list.md missing"
    text = script.read_text(encoding="utf-8")
    if "0:00–0:25" not in text or "4:20–4:45" not in text:
        return False, "script does not bookend the 0:00–4:45 timeline"
    return True, "script + shot list present, timeline 4:30–4:45"


def gate_video_file_present() -> tuple[bool, str]:
    """Optional gate: only enforced under --strict (recording happens in Week 4)."""

    video = _exists("evidence/phase2_video.mp4")
    if not video.exists():
        return False, "evidence/phase2_video.mp4 not yet recorded"
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return False, "ffprobe not on PATH (cannot verify duration)"
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return False, f"ffprobe failed: {proc.stderr.strip()}"
    try:
        duration = float(proc.stdout.strip())
    except ValueError:
        return False, f"ffprobe output not a float: {proc.stdout!r}"
    if duration > 300.0:
        return False, f"duration {duration:.1f} s > 5:00"
    return True, f"duration {duration:.1f} s (≤ 5:00)"


def gate_submission_zip() -> tuple[bool, str]:
    zip_path = _exists("releases/PHASE2_SUBMISSION.zip")
    if not zip_path.exists():
        return False, "releases/PHASE2_SUBMISSION.zip not yet assembled (Week 5)"
    return True, f"zip size {zip_path.stat().st_size} B"


# ---------------------------------------------------------------------------
# CLI driver
# ---------------------------------------------------------------------------


def run_all(strict: bool = False) -> Verifier:
    v = Verifier()
    v.add(
        "Embedded C99 model compiles (gcc -std=c99 -Wall -Wextra -Werror)",
        gate_embedded_c99_compiles,
    )
    v.add("Golden-vector header + parity_runner compile", gate_golden_vectors_compile)
    v.add("Parity report: pass, no stubs, max prob error ≤ 1e-4", gate_parity_report)
    v.add("Embedded resource estimate present", gate_resource_estimate)
    v.add("Energy-policy summary (fixed vs ml)", gate_energy_policy)
    v.add(
        "Simulation artifact (Ansys manifest or radio-link sim)",
        gate_simulation_artifact,
    )
    v.add("Test suite (`pytest -q`) is green", gate_test_suite)
    v.add("Project Description ≤ 1050 words", gate_project_description_word_count)
    v.add("Video script + shot list drafts", gate_video_script_draft, mandatory=strict)
    v.add(
        "Video ≤ 5:00 (evidence/phase2_video.mp4)",
        gate_video_file_present,
        mandatory=strict,
    )
    v.add(
        "Submission zip present (releases/PHASE2_SUBMISSION.zip)",
        gate_submission_zip,
        mandatory=strict,
    )
    return v


def render_table(v: Verifier) -> str:
    lines = ["THERMAL-NEXUS Phase-2 verification", "=" * 78]
    for gate in v.gates:
        lines.append(gate.as_row())
    lines.append("=" * 78)
    failed = v.failed()
    mandatory_failed = [g for g in failed if g.mandatory]
    optional_failed = [g for g in failed if not g.mandatory]
    if not failed:
        lines.append("All gates PASS.")
    else:
        lines.append(
            f"{len(failed)} gate(s) failed: "
            f"{len(mandatory_failed)} mandatory, {len(optional_failed)} optional."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also enforce optional gates (video, zip).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Machine-readable JSON output."
    )
    args = parser.parse_args(argv)

    v = run_all(strict=args.strict)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": g.name,
                        "status": g.status,
                        "detail": g.detail,
                        "mandatory": g.mandatory,
                    }
                    for g in v.gates
                ],
                indent=2,
            )
        )
    else:
        print(render_table(v))

    mandatory_fails = [g for g in v.failed() if g.mandatory]
    return 1 if mandatory_fails else 0


if __name__ == "__main__":
    sys.exit(main())
