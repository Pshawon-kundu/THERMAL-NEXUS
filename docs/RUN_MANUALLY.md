# THERMAL-NEXUS — Manual Run Guide

This guide walks through how to run the THERMAL-NEXUS project on a clean machine.

All commands assume the repository root as the working directory:

```bash
cd "/Users/joy0x1/Downloads/HART Project/THERMAL-NEXUS"
```

---

## 1. Activate the Python environment

```bash
source .venv/bin/activate
```

If the virtual environment does not exist:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Verify:

```bash
python --version
pytest --version
```

---

## 2. Run the complete verification

This is the fastest first check.

```bash
python -m scripts.verify_phase2
```

Expected result:

```text
65 passed, 6 skipped
0 mandatory Phase-2 gates failing
```

The two always-deferred checks are expected until the video and final
submission ZIP are created.

For machine-readable output:

```bash
python -m scripts.verify_phase2 --json
```

For strict final-submission checking:

```bash
python -m scripts.verify_phase2 --strict
```

`--strict` will fail until these files exist:

```text
evidence/phase2_video.mp4
releases/PHASE2_SUBMISSION.zip
```

---

## 3. Generate the custom dataset

The primary project dataset is stored at:

```text
Datasets/CustomDataset/
```

To regenerate the raw temperature scenarios:

```bash
python -m simulator.temperature.generate \
  --config config/scenarios.yaml \
  --all \
  --runs 8 \
  --output-dir Datasets/CustomDataset/raw
```

This produces:

- 12 scenarios
- 8 runs per scenario
- 96 runs total
- approximately 12,000 model-ready rows

Available scenarios:

```text
stable_cold
stable_room
gradual_warming
rapid_warming
cold_to_ambient
ambient_to_cold
short_door_opening
long_door_opening
repeated_door_opening
sudden_spike
sensor_drift
missing_samples
temporary_sensor_fault
```

Generate a single scenario:

```bash
python -m simulator.temperature.generate \
  --config config/scenarios.yaml \
  --scenario gradual_warming \
  --runs 1 \
  --output-dir ml/data/manual_run
```

---

## 4. Build features and labels

```bash
python -m ml.preprocessing.build_dataset \
  --input Datasets/CustomDataset/raw \
  --label-config config/labeling.yaml \
  --feature-config config/features.yaml
```

Outputs:

```text
ml/data/processed/labeled_feature_rows.csv
ml/data/processed/model_ready_dataset.csv
ml/data/processed/dataset_manifest.csv
```

If you regenerated the raw files, copy the processed files back into the
custom dataset folder:

```bash
cp ml/data/processed/labeled_feature_rows.csv \
   Datasets/CustomDataset/processed/

cp ml/data/processed/model_ready_dataset.csv \
   Datasets/CustomDataset/processed/

cp ml/data/processed/dataset_manifest.csv \
   Datasets/CustomDataset/processed/
```

---

## 5. Create leakage-safe train/validation/test splits

```bash
python -m ml.preprocessing.split_dataset \
  --input ml/data/processed/model_ready_dataset.csv \
  --output ml/data/splits
```

Copy the split files into the custom dataset folder:

```bash
cp ml/data/splits/train.csv \
   Datasets/CustomDataset/splits/

cp ml/data/splits/validation.csv \
   Datasets/CustomDataset/splits/

cp ml/data/splits/test.csv \
   Datasets/CustomDataset/splits/

cp ml/data/splits/split_manifest.csv \
   Datasets/CustomDataset/splits/
```

The split policy is grouped by `run_id`, which prevents samples from one
run appearing in both training and testing.

---

## 6. Train all models

```bash
python -m ml.training.train_models \
  --config config/models.yaml
```

This trains:

- Logistic regression
- Decision tree
- Random forest reference model
- Small MLP
- Fixed threshold baseline
- Rule-based baseline

Reports are written to:

```text
evidence/models/
```

Key files:

```text
evidence/models/model_comparison.csv
evidence/models/model_comparison.md
evidence/models/validation_metrics.json
evidence/models/final_test_metrics.json
evidence/models/model_selection_report.md
```

Models are written to:

```text
ml/models/candidates/
ml/models/selected/
```

---

## 7. Evaluate the selected model on the test split

The current embedded-deployable model is logistic regression:

```bash
python -m ml.evaluation.evaluate_final_model \
  --model ml/models/selected/provisional_20260731_200938_logistic_regression \
  --test ml/data/splits/test.csv \
  --confirm-test-evaluation
```

The final test report is written to:

```text
evidence/models/final_test_metrics.json
```

---

## 8. Export the model to embedded C99

The embedded export uses the model referenced by:

```text
ml/models/selected/latest_selected.json
```

Run:

```bash
python -m embedded.deployment.prepare_export
```

This generates:

```text
embedded/generated/thermal_nexus_model.c
embedded/generated/thermal_nexus_model.h
embedded/generated/thermal_nexus_model_metadata.json
embedded/golden_vectors/golden_vectors.json
embedded/golden_vectors/golden_vectors.h
evidence/embedded/parity_report.json
evidence/embedded/resource_estimate.json
```

---

## 9. Run embedded parity tests

Quick run:

```bash
pytest -q tests/test_embedded_parity_phase2.py
```

Full embedded parity and unit suite:

```bash
pytest -q embedded/tests/test_parity.py
```

Expected parity result:

```text
Maximum probability error: approximately 2.60e-07
Class mismatches: 0
Uniform stubs: 0
```

---

## 10. Run the end-to-end simulation

Check available options first:

```bash
python simulator/run_end_to_end.py --help
```

Then run:

```bash
python simulator/run_end_to_end.py \
  --config config/scenarios.yaml
```

Generated experiment evidence is stored under:

```text
evidence/end_to_end/
```

Typical operating modes:

```text
fixed
rule_based
ml
```

---

## 11. Run the energy-policy comparison

```bash
python -m analysis.energy_policy_report
```

Outputs:

```text
evidence/ai/energy_policy_comparison.csv
evidence/ai/energy_policy_summary.json
evidence/ai/energy_policy_figure.png
evidence/ai/energy_policy_report.md
```

These compare:

- Fixed transmission
- Rule-based transmission
- ML/event-driven transmission

All energy numbers are software estimates and must remain labelled as
estimated until hardware current measurements are available.

---

## 12. Run the radio-link simulation

```bash
python simulation/radio_link/run_radio_simulation.py
```

Outputs:

```text
simulation/radio_link/results/path_loss_sweep.csv
simulation/radio_link/results/per_vs_distance.csv
simulation/radio_link/results/link_budget.json
simulation/radio_link/results/link_budget_figure.png
```

---

## 13. Start the dashboard

Check the dashboard help:

```bash
python -m host.dashboard.app --help
```

Then start Streamlit:

```bash
streamlit run host/dashboard/app.py
```

Open the local URL shown by Streamlit, usually:

```text
http://localhost:8501
```

The dashboard contains pages for:

- Overview
- Experiments
- Live simulation
- Replay
- Mode comparison
- Radio reader
- Alerts
- KPI reports
- Model readiness
- Hardware
- System information

The dashboard is currently designed for offline/local use.

---

## 14. Run tests manually

Full test suite:

```bash
pytest -q
```

Run a specific area:

```bash
pytest -q tests/test_dashboard_phase.py
pytest -q tests/test_energy_policy.py
pytest -q tests/test_embedded_parity_phase2.py
pytest -q tests/test_phase2_verification.py
pytest -q tests/test_training_pipeline.py
```

Run with verbose output:

```bash
pytest -v
```

Run external T15 tests, only if raw T15 files are present:

```bash
pytest -m external_t15
```

Run hardware-gated tests:

```bash
pytest --runs-hardware
```

---

## 15. Audit the supplied external datasets

Audit only:

```bash
python scripts/prepare_external_dataset.py --audit-only
```

Convert compatible Nepal files:

```bash
python scripts/prepare_external_dataset.py \
  --convert \
  --max-nepal-files 50
```

Convert all compatible Nepal traces:

```bash
python scripts/prepare_external_dataset.py \
  --convert
```

Include the ELM source as well:

```bash
python scripts/prepare_external_dataset.py \
  --convert \
  --include-elm
```

The converted external data is stored at:

```text
ml/data/external/thermal_nexus/
```

It should be treated as auxiliary domain-shift evidence, not as the
primary training set.

---

## 16. Recommended full manual workflow

If you want to regenerate and verify everything from scratch, use:

```bash
cd "/Users/joy0x1/Downloads/HART Project/THERMAL-NEXUS"

source .venv/bin/activate

python -m simulator.temperature.generate \
  --config config/scenarios.yaml \
  --all \
  --runs 8 \
  --output-dir Datasets/CustomDataset/raw

python -m ml.preprocessing.build_dataset \
  --input Datasets/CustomDataset/raw \
  --label-config config/labeling.yaml \
  --feature-config config/features.yaml

python -m ml.preprocessing.split_dataset \
  --input ml/data/processed/model_ready_dataset.csv \
  --output ml/data/splits

python -m ml.training.train_models \
  --config config/models.yaml

python -m embedded.deployment.prepare_export

python -m pytest -q

python -m scripts.verify_phase2
```

For a quick normal run without retraining:

```bash
cd "/Users/joy0x1/Downloads/HART Project/THERMAL-NEXUS"
source .venv/bin/activate
python -m scripts.verify_phase2
streamlit run host/dashboard/app.py
```

---

## 17. Dataset categories

The project contains three distinct data categories. Do not mix them
without preserving their source labels and limitations.

### Primary native training dataset

```text
Datasets/CustomDataset/
```

Controlled, reproducible synthetic temperature dataset. Primary training
corpus for the deployed embedded logistic-regression model.

### Converted external T15 dataset

```text
ml/data/external/t15/
```

Separate external T15 benchmark, gated as an integration dataset.

### Auxiliary domain-shift evidence

```text
ml/data/external/thermal_nexus/
```

Converted ELM and Nepal carrier data. Auxiliary domain-shift evidence,
not the primary training set.

---

## 18. Build the Phase-2 PDF report (optional)

If a TeX toolchain is installed:

```bash
cd docs
pdflatex work_completed_report.tex
pdflatex work_completed_report.tex
```

The two-pass build correctly resolves the document structure.

---

## 19. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | venv not active | `source .venv/bin/activate` |
| `pytest: command not found` | venv not active | `source .venv/bin/activate` |
| Embedded C99 fails | No C compiler | Install `gcc` or `clang` |
| External T15 tests skip | Raw T15 data missing | Place `NEW-DATA-*.T15.txt` under `ml/data/external/t15/raw/` |
| `prepare_export.py` says no model selected | `latest_selected.json` missing | Run `python -m ml.training.train_models --config config/models.yaml` |
| Verify script fails parity gate | Old C99 export | Run `python -m embedded.deployment.prepare_export` |
| Streamlit blank page | Wrong entry point | Use `streamlit run host/dashboard/app.py` |
| `ModuleNotFoundError: matplotlib` | Missing deps | `pip install matplotlib numpy pandas PyYAML` |
| `pyarrow` import errors | Wrong Py version | Use Python 3.10+ |
| Empty predictions | Class imbalance | Verify `class_weight: balanced` in `config/models.yaml` |

---

## 20. Quick reference

| Script | Purpose |
|---|---|
| `python -m scripts.verify_phase2` | Run all Phase-2 gates |
| `python -m simulator.temperature.generate` | Generate synthetic temperature data |
| `python -m ml.preprocessing.build_dataset` | Build features and labels |
| `python -m ml.preprocessing.split_dataset` | Create leakage-safe splits |
| `python -m ml.training.train_models` | Train all candidate models |
| `python -m ml.evaluation.evaluate_final_model` | Evaluate selected model on test set |
| `python -m embedded.deployment.prepare_export` | Export model to C99 |
| `python -m analysis.energy_policy_report` | Generate energy-policy comparison |
| `python simulation/radio_link/run_radio_simulation.py` | Run radio-link simulation |
| `python scripts/prepare_external_dataset.py` | Audit and convert external datasets |
| `streamlit run host/dashboard/app.py` | Start the dashboard |
| `pytest -q` | Run the full test suite |

---

## 21. Output file locations

After a full run, the important output files are:

```text
Datasets/CustomDataset/raw/
Datasets/CustomDataset/processed/model_ready_dataset.csv
Datasets/CustomDataset/splits/{train,validation,test}.csv

ml/data/external/thermal_nexus/

ml/data/splits/{train,validation,test}.csv
ml/models/selected/latest_selected.json
ml/models/selected/provisional_*/
ml/models/candidates/

embedded/generated/thermal_nexus_model.{c,h}
embedded/golden_vectors/golden_vectors.{h,json}

evidence/models/model_comparison.csv
evidence/models/final_test_metrics.json
evidence/embedded/parity_report.json
evidence/embedded/resource_estimate.json
evidence/ai/energy_policy_summary.json
evidence/ai/energy_policy_figure.png
evidence/ai/energy_policy_report.md
evidence/end_to_end/{fixed,rule_based,ml}/

simulation/radio_link/results/{path_loss_sweep,per_vs_distance}.csv
simulation/radio_link/results/link_budget.json
simulation/radio_link/results/link_budget_figure.png
simulation/ansys/manifest.json
```

---

## 22. Disclaimer

All temperature and energy values produced by this project are
software-simulated. They are not hardware measurements. Until the
fabricated Phase-2 demonstrator provides measured current-probe data,
all energy numbers must be quoted with their `ESTIMATED_SOFTWARE_VALUE`
label.
