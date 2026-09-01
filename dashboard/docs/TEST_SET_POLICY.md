# Test Set Policy

The test split is locked during candidate development.

Allowed during candidate training:

- training split fitting
- training split group-aware CV
- external validation split model selection
- validation-only baseline comparison

Disallowed during candidate training:

- reading `test.csv` for model selection
- repeated test optimization
- threshold tuning on test data

Final test evaluation requires:

```powershell
python -m ml.evaluation.evaluate_final_model --model ml/models/selected --test ml/data/splits/test.csv --confirm-test-evaluation
```

Without `--confirm-test-evaluation`, the command fails. Final test metrics are written to `evidence/models/final_test_metrics.json` only after explicit confirmation.

