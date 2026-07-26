# Thermal Nexus

Thermal Nexus is a software-only digital prototype for an AI-assisted predictive
long-range wireless temperature-monitoring system for cold-chain logistics.

The project covers the full Phase 1–7 IEEE HART HardwAIre Challenge 2026 scope
in software: synthetic data, baselines, lightweight ML, end-to-end protocol
simulation, offline Streamlit dashboard, hardware-independent embedded export,
and a swappable TMP117 + STM32U585 + XBee-PRO 900HP hardware simulator that
mirrors the eventual MCU firmware.

All energy, range, accuracy, packet, and KPI outputs are **simulated
software-estimated** values unless explicitly replaced by real hardware
measurements. The disclaimer banner in the dashboard reads
`SIMULATED SOFTWARE DATA - NOT PHYSICAL HARDWARE RESULTS`.

## Repository layout

```
analysis/        KPI engine, baselines, EDA, dataset health, runtime metrics
config/          YAML configs (scenarios, features, models, baselines, etc.)
docs/            Specifications and policy documents
embedded/        C99 model export, golden vectors, parity tests
evidence/        Generated dataset audits, KPI reports, comparison outputs
experiments/     Imported end-to-end experiment batches
host/            Database, ingestion, replay engine, dashboard, queries
ml/              Preprocessing, training, evaluation, inference, deployment
protocol/        Wireless packet encoding/decoding
releases/        Build artifacts for the embedded binary
simulator/       Temperature, radio, reader, end-to-end, and hardware phases
tests/           Pytest suite
tools/           PowerShell + bash launchers for each phase
```

## Setup

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### macOS / Linux (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Tests and quality checks

```powershell
python -m pytest
python -m ruff check .
python -m black --check .
```

Or one-shot:

```powershell
.\tools\run_tests.ps1
```

macOS / Linux equivalent:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m black --check .
```

## Phase 1 — Synthetic data generation

Generate five gradual warming runs:

```powershell
python -m simulator.temperature.generate --config config/scenarios.yaml --scenario gradual_warming --runs 5
```

Generate three runs for every configured scenario:

```powershell
python -m simulator.temperature.generate --config config/scenarios.yaml --all --runs 3
```

Or:

```powershell
.\tools\generate_demo_data.ps1
```

Outputs are written under `ml/data/synthetic/` by default. Each run creates:

- CSV data
- metadata JSON
- PNG temperature plot

Raw generated data should be treated as immutable evidence for a run. Create new runs rather than manually editing generated CSV files.

## Phase 2 — Preprocessing, labels, splits

Audit generated synthetic runs:

```powershell
python -m ml.preprocessing.audit_dataset --input ml/data/synthetic
```

Build labels and past-only features:

```powershell
python -m ml.preprocessing.build_dataset --input ml/data/synthetic --label-config config/labeling.yaml --feature-config config/features.yaml
```

Create run-level train/validation/test splits:

```powershell
python -m ml.preprocessing.split_dataset --input ml/data/processed/model_ready_dataset.csv --output ml/data/splits
```

Or run the full preprocessing phase:

```powershell
.\tools\build_ml_dataset.ps1
```

If PowerShell script execution is disabled on the machine, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_ml_dataset.ps1
```

## Leakage and Ground Truth Policy

Synthetic labels use `true_temperature` because the simulator knows the ground-truth thermal curve. Model input features use only current and past `measured_temperature` values and current limits. Future target helper columns are excluded from `model_ready_dataset.csv`.

Invalid or missing sensor samples are explicitly marked and receive `feature_valid=false` with a reason. They are not silently imputed.

No model is trained in this phase. Future competition claims require real hardware measurements, and future models must be retrained or validated using real TMP117 data.

## Phase 3 — EDA and baselines

Run dataset health, EDA, fixed-threshold baseline, rule-based baseline, and baseline evaluation:

```powershell
python -m analysis.dataset_health --train ml/data/splits/train.csv --validation ml/data/splits/validation.csv --test ml/data/splits/test.csv
python -m analysis.eda --train ml/data/splits/train.csv --output evidence/eda
python -m ml.evaluation.evaluate_baselines --train ml/data/splits/train.csv --validation ml/data/splits/validation.csv --test ml/data/splits/test.csv --config config/baselines.yaml
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_baseline_analysis.ps1
```

The fixed-threshold baseline is reactive: it alerts only after measured temperature is already outside limits. The rule-based baseline is a non-learned predictive comparison using current and historical features only. Thresholds are configured and must be selected from training data only.

## Phase 4 — TinyML modeling

Train candidate models using train plus validation only:

```powershell
python -m ml.training.train_models --config config/models.yaml
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\train_candidate_models.ps1
```

Final test evaluation is locked and must be explicitly confirmed:

```powershell
python -m ml.evaluation.evaluate_final_model --model ml/models/selected --test ml/data/splits/test.csv --confirm-test-evaluation
```

The trained model is provisional and based on synthetic software data. It is not an embedded artifact and is not a hardware result.

## Phase 5 — End-to-end software simulation

Run the three operating modes against one generated synthetic run:

```powershell
.\tools\run_end_to_end_demo.ps1
```

Equivalent direct command:

```powershell
python -m simulator.run_end_to_end `
  --scenario gradual_warming `
  --runs 1 `
  --modes fixed rule_based ml `
  --radio-config config/radio_simulation.yaml `
  --policy-config config/runtime_policy.yaml `
  --output evidence/end_to_end
```

Outputs are written under `evidence/end_to_end/`. Energy values are labeled
`ESTIMATED SOFTWARE VALUE`; they are not measured hardware energy, range, or
accuracy claims.

## Phase 6 — Offline dashboard, KPI, embedded preparation

Initialize the local SQLite database and import end-to-end evidence:

```powershell
.\tools\initialize_dashboard.ps1
.\tools\import_latest_experiments.ps1
```

Generate KPI reports:

```powershell
.\tools\generate_kpi_reports.ps1
```

Run the offline dashboard:

```powershell
.\tools\run_dashboard.ps1
```

Prepare hardware-independent embedded export artifacts:

```powershell
.\tools\prepare_embedded_export.ps1
.\tools\run_embedded_parity.ps1
```

Run the dashboard-phase verification workflow:

```powershell
.\tools\verify_dashboard_phase.ps1
```

All dashboard, KPI, radio, energy, and embedded-readiness outputs are
preliminary software results unless later replaced by real TMP117, STM32U585,
XBee-PRO, and reader measurements.

### Dashboard pages (sidebar)

The dashboard registers 11 pages via `st.navigation`. Click any entry in the
left sidebar to switch; each page has its own URL (`/overview`,
`/experiments`, …).

| Page | Source module | Purpose |
|------|---------------|---------|
| Overview | `pages/overview.py` | System metrics, mode chart, runtime config |
| Experiments | `pages/experiments.py` | Filterable experiment browser + JSON detail |
| Live Simulation | `pages/live_simulation.py` | Subprocess launcher for `simulator.run_end_to_end` |
| Replay | `pages/replay.py` | `node_decisions` table per experiment |
| Mode Comparison | `pages/mode_comparison.py` | KPI bar chart across fixed / rule_based / ml |
| Radio & Reader | `pages/radio_reader.py` | Combined `radio_events` + `reader_records` table |
| Alerts | `pages/alerts.py` | Filterable alerts / faults table |
| KPI Reports | `pages/kpi_reports.py` | Full KPI dataframe (raw rows) |
| Model Readiness | `pages/model_readiness.py` | `embedded/generated/deployment_manifest.json` |
| Hardware | `pages/hardware.py` | Phase-2 hardware-phase KPI block + charts |
| System Info | `pages/system_info.py` | Raw `config/dashboard.yaml` + Python version |

## Phase 6 — Hardware phase (simulated)

The hardware phase runs entirely in software today. The `--source` flag on the
hardware demo flips between `simulated` and `measured`; the `measured` path
is the integration point for real TMP117 + STM32U585 + XBee-PRO 900HP
firmware (Phase 7).

```powershell
.\tools\run_hardware_demo.ps1
# or with a custom output directory:
.\tools\run_hardware_demo.ps1 -Output evidence\hardware\run_001
# or with the eventual measured source:
.\tools\run_hardware_demo.ps1 -Source measured
```

macOS / Linux equivalent (one-shot):

```bash
bash tools/run_hardware_phase_macos.sh            # simulated
bash tools/run_hardware_phase_macos.sh measured   # measured (Phase 7)
```

After the campaign, refresh the hardware tab in the dashboard:

```powershell
.\tools\refresh_hardware_dashboard_tab.ps1
```

Run the hardware-phase verification:

```powershell
.\tools\verify_hardware_phase.ps1
```

The hardware demo emits these artifacts into `evidence/hardware/<run_id>/`:

- `range_test.csv`, `accuracy_test.csv` — measured telemetry
- `bom.csv` — Bill of Materials + cost / weight / volume totals
- `hardware_run.json` — run-level summary (range, accuracy, source, firmware)
- `parity.json` — embedded-vs-Python parity check result
- `log.txt` — full simulator trace

Phase-2 acceptance thresholds (soft targets):

| KPI | Target | Simulated result |
|-----|--------|------------------|
| Range with PER < 50% | ≥ 60 m | 250 m |
| Accuracy (max abs error) | ≤ ±0.5 °C | ±0.10 °C |
| BoM cost | ≤ $75 USD | $68.50 |
| Weight per node | ≤ 80 g | 52.7 g |
| Volume | ≤ 250 cm³ | 92 cm³ |

Swap from simulated → measured by running the same launcher with
`-Source measured` once Phase 7 firmware is connected.

## External T15 benchmark (separate phase)

The external T15 dataset is a separate benchmark used only for parser,
temporal-feature validation, dashboard/replay testing, and external robustness.
It is **not** part of project-collected cold-chain claims.

```powershell
# Convert the external source CSV into the Thermal Nexus schema
.venv/bin/python tools/convert_t15_to_thermal_nexus.py
.\tools\build_external_t15_dataset.ps1
.\tools\run_external_t15_audit.ps1
.\tools\train_external_t15_models.ps1
.\tools\evaluate_external_t15_models.ps1
.\tools\verify_external_t15_phase.ps1
```

This phase is gated on `config/external_t15.yaml` and is opt-in.

## Test suite summary

The pytest suite covers the seven phases plus contract / regression tests:

| Test file | Phase |
|-----------|-------|
| `tests/test_temperature_generator.py` | Phase 1 synthetic data |
| `tests/test_ml_preprocessing.py` | Phase 2 features, labels, splits |
| `tests/test_baseline_analysis.py` | Phase 3 baselines + dataset health |
| `tests/test_training_pipeline.py` | Phase 4 candidate models + selected export |
| `tests/test_runtime_simulation.py` | Phase 5 end-to-end simulation |
| `tests/test_dashboard_phase.py` | Phase 6 dashboard + ingestion + KPI + embedded export + router |
| `tests/test_external_t15_pipeline.py` | External T15 benchmark (opt-in) |

Run a single phase:

```powershell
python -m pytest tests/test_dashboard_phase.py -q
python -m pytest tests/test_runtime_simulation.py -q
```

## Conventions

- All commands assume the repository root as the working directory.
- All Python invocations inside the `tools/` launchers use `.venv` — re-create
  it before running.
- All energy, range, accuracy, packet, and KPI numbers in the dashboard,
  evidence, and reports are **simulated software-estimated** values. Real
  hardware measurements replace them in Phase 7.
- Schema migrations live in `host/database/migrations.py`. The current
  schema version is 2 (adds `hardware_runs`, `measurement_traces`,
  `bom_items`, `physical_measurements`, and `alerts.source_event_id`).
