# THERMAL_NEXUS_TEMP_DEV_V1

Status: FROZEN_DEVELOPMENT_DATASET

Purpose: reproducible temperature-only forecasting development benchmark.

Approved sources: Intel Berkeley Lab, UCI Room Occupancy Estimation, and
Bolzano IEQ. All accepted rows are EXTERNAL_DERIVED_BENCHMARK. Raw rows are
retained and checksummed.

Rows: canonical 316657; model-ready 4968. Source composition:
Intel 168, UCI 1800, Bolzano 3000. PROJECT_COLLECTED 0; SYNTHETIC 0; T15
excluded.

Processing: 16-32 C eligibility filter, 5-minute mean resampling, segmentation
at gaps over 10 minutes, no large-gap interpolation. Features use only
historical temperature. Targets are timestamp-based 5/15/30-minute future
temperatures and do not cross runs.

Frozen splits:
train 3468 rows/58 runs;
validation 750 rows/
6 runs;
test 750 rows/3 runs.
TEST_SET_USED=true.

Observed model-ready range: 16.600-28.145 C. This is not
full 16-32 C coverage. Dynamics: stable 72.58%,
warming 11.17%,
cooling 16.24%.

Integrity: duplicate, leakage, split-overlap, checksum, and reproducibility
audits are recorded beside this card.

Prior development evaluation found persistence outperformed ML. Temp V2 is a
derived modelling view and does not alter this frozen source dataset.

Prohibited claims: this is not PROJECT_COLLECTED, final Thermal Nexus field
validation, cold-chain validated, vaccine validated, organ validated, full
16-32 C validated, or biological outcome prediction.
