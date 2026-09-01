# Runtime Inference Specification

The runtime wrapper loads the selected model artifact from `ml/models/selected`
without retraining. It requires a pipeline or model artifact, preprocessing
artifact, frozen feature order, class mapping, configuration, model card, and
checksums.

Inputs are validated against the frozen feature list. Future labels, targets,
`true_temperature`, `scenario`, and `run_id` are rejected as predictor inputs.
NaN and infinite values are rejected. When the model cannot be loaded or
inference fails, the runtime returns `MODEL_FAULT` and records the fallback
reason.

All results are preliminary software simulation results.
