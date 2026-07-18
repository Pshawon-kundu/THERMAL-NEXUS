# Model Artifact Specification

Every candidate model run writes a versioned directory under:

```text
ml/models/candidates/<model_name>/<training_timestamp>/
```

Required files:

- `model.joblib`
- `pipeline.joblib`
- `preprocessing.joblib`
- `feature_schema.json`
- `class_mapping.json`
- `configuration.yaml`
- `metrics_validation.json`
- `MODEL_CARD.md`
- `checksums.json`

The selected provisional model is copied under:

```text
ml/models/selected/provisional_<timestamp>_<model_name>/
```

`ml/models/selected/latest_selected.json` points to the active selected artifact. Candidate artifact directories are versioned to avoid silent overwrites.

Artifact size is measured from persisted joblib files. Inference latency is measured on the current computer as per-row prediction time over a bounded validation sample.

