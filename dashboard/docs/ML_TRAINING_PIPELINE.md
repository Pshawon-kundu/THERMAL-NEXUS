# ML Training Pipeline

The supervised training phase trains only lightweight scikit-learn candidates:

- Logistic Regression
- Small Decision Tree
- Small Random Forest reference
- Small MLP

The pipeline loads train and validation splits separately. It does not concatenate all splits before fitting, and it does not read `test.csv` during candidate training.

Preprocessing objects such as scalers are fitted on training data only. Validation data is transformed with already-fitted preprocessing. Unexpected NaN, infinity, feature-invalid rows, or unavailable targets cause a clear failure.

Group-aware cross-validation is performed inside the training split using complete `run_id` groups. External validation remains reserved for final candidate and hyperparameter selection.

No LSTM, GRU, CNN, Transformer, embedded firmware, TensorFlow Lite Micro conversion, radio simulation, or dashboard work is included in this phase.

