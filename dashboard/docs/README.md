# THERMAL-NEXUS Documentation Index

This directory holds project documentation, organised by topic. Use the
table below as a starting point — most readers only need three or four
documents for a given concern.

## Dataset locations

| Dataset | Purpose |
|---|---|
| [`../Datasets/CustomDataset/`](../Datasets/CustomDataset/) | Primary THERMAL-NEXUS synthetic training dataset: 96 runs, 12 scenarios, 12,584 model-ready rows. |
| [`../Datasets/`](../Datasets/) | Supplied external ELM, Nepal vaccine-carrier, and research sources. |
| [`../ml/data/external/thermal_nexus/`](../ml/data/external/thermal_nexus/) | Provenance-preserving conversion of compatible external temperature traces; auxiliary domain-shift evidence only. |


|---|---|
| [`RUN_MANUALLY.md`](RUN_MANUALLY.md) | Complete manual run, training, dashboard, testing, and troubleshooting guide. |
| [`project_description_2page.md`](project_description_2page.md) | 2-page (≤ 1050 word) project description draft. |
| [`video_script_5min.md`](video_script_5min.md) | Voice-over script for the 5-minute video (target 4:30–4:45). |
| [`video_shot_list.md`](video_shot_list.md) | Shot-by-shot list with overlays and badges. |

Run `python -m scripts.verify_phase2` from the repo root to confirm
the mandatory Phase-2 gates (C99 compile, parity, energy policy,
simulation artefact, tests, etc.).

## Architecture and subsystem specifications

| Subsystem | Specification |
|---|---|
| System overview | [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) |
| Runtime inference | [`RUNTIME_INFERENCE_SPECIFICATION.md`](RUNTIME_INFERENCE_SPECIFICATION.md) |
| Adaptive policy | [`ADAPTIVE_POLICY_SPECIFICATION.md`](ADAPTIVE_POLICY_SPECIFICATION.md) |
| Baseline policy | [`BASELINE_SPECIFICATION.md`](BASELINE_SPECIFICATION.md), [`BASELINE_EVALUATION_POLICY.md`](BASELINE_EVALUATION_POLICY.md) |
| Sensor node simulator | [`SENSOR_NODE_SIMULATOR.md`](SENSOR_NODE_SIMULATOR.md) |
| Radio simulator | [`RADIO_SIMULATOR.md`](RADIO_SIMULATOR.md) |
| Reader simulator | [`READER_SIMULATOR.md`](READER_SIMULATOR.md) |

## Data and ML pipeline

| Document | Purpose |
|---|---|
| ML problem definition | [`ML_PROBLEM_DEFINITION.md`](ML_PROBLEM_DEFINITION.md) |
| Dataset specification | [`DATASET_SPECIFICATION.md`](DATASET_SPECIFICATION.md) |
| Feature schema / spec | [`FEATURE_SCHEMA.md`](FEATURE_SCHEMA.md), [`FEATURE_SPECIFICATION.md`](FEATURE_SPECIFICATION.md) |
| Labeling specification | [`LABELING_SPECIFICATION.md`](LABELING_SPECIFICATION.md) |
| Data splitting policy | [`DATA_SPLITTING_POLICY.md`](DATA_SPLITTING_POLICY.md) |
| Test-set policy | [`TEST_SET_POLICY.md`](TEST_SET_POLICY.md) |
| Model artifact spec | [`MODEL_ARTIFACT_SPECIFICATION.md`](MODEL_ARTIFACT_SPECIFICATION.md) |
| Model selection policy | [`MODEL_SELECTION_POLICY.md`](MODEL_SELECTION_POLICY.md) |
| ML training pipeline | [`ML_TRAINING_PIPELINE.md`](ML_TRAINING_PIPELINE.md) |
| External T15 dataset | [`EXTERNAL_T15_DATASET.md`](EXTERNAL_T15_DATASET.md) |
| Preliminary model results | [`PRELIMINARY_MODEL_RESULTS_GUIDE.md`](PRELIMINARY_MODEL_RESULTS_GUIDE.md) |
| EDA report guide | [`EDA_REPORT_GUIDE.md`](EDA_REPORT_GUIDE.md) |

## Embedded deployment

| Document | Purpose |
|---|---|
| Embedded deployment | [`EMBEDDED_DEPLOYMENT_SPECIFICATION.md`](EMBEDDED_DEPLOYMENT_SPECIFICATION.md) |
| Protocol v1 | [`PROTOCOL_V1_SPECIFICATION.md`](PROTOCOL_V1_SPECIFICATION.md) |
| Golden vectors | [`GOLDEN_VECTOR_SPECIFICATION.md`](GOLDEN_VECTOR_SPECIFICATION.md) |
| Parity test guide | [`PARITY_TEST_GUIDE.md`](PARITY_TEST_GUIDE.md) |

## Host, dashboard, and experiments

| Document | Purpose |
|---|---|
| End-to-end simulation guide | [`END_TO_END_SIMULATION_GUIDE.md`](END_TO_END_SIMULATION_GUIDE.md) |
| Offline dashboard guide | [`OFFLINE_DASHBOARD_GUIDE.md`](OFFLINE_DASHBOARD_GUIDE.md) |
| Experiment data contract | [`EXPERIMENT_DATA_CONTRACT.md`](EXPERIMENT_DATA_CONTRACT.md) |
| Experiment ingestion guide | [`EXPERIMENT_INGESTION_GUIDE.md`](EXPERIMENT_INGESTION_GUIDE.md) |
| Experiment replay guide | [`EXPERIMENT_REPLAY_GUIDE.md`](EXPERIMENT_REPLAY_GUIDE.md) |
| KPI definition catalog | [`KPI_DEFINITION_CATALOG.md`](KPI_DEFINITION_CATALOG.md) |
| KPI reporting guide | [`KPI_REPORTING_GUIDE.md`](KPI_REPORTING_GUIDE.md) |

## Compliance and roadmap

| Document | Purpose |
|---|---|
| Dashboard phase limitations | [`DASHBOARD_PHASE_LIMITATIONS.md`](DASHBOARD_PHASE_LIMITATIONS.md) |
| Phase dashboard audit | [`PHASE_DASHBOARD_AUDIT.md`](PHASE_DASHBOARD_AUDIT.md) |
| Software roadmap | [`SOFTWARE_ROADMAP.md`](SOFTWARE_ROADMAP.md) |
