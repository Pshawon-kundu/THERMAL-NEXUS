# Model Selection Policy

The provisional selected model is chosen from validation results using a configurable multi-criteria score, not accuracy alone.

Priority order:

1. `EXCURSION_RISK` recall
2. Missed-event rate
3. Warning lead time
4. Macro F1
5. `TRANSITION` recall
6. False-alarm rate
7. Artifact size
8. Inference latency
9. Embedded interpretability and implementation complexity

Models are rejected when they fail the configured minimum `EXCURSION_RISK` recall or maximum missed-event threshold. The Random Forest is labeled as `REFERENCE_MODEL_NOT_YET_APPROVED_FOR_EMBEDDED_DEPLOYMENT` and is excluded from automatic provisional deployment selection.

The selected model is provisional because it is trained on synthetic software data. It must be retrained and validated using real TMP117 runs before hardware or competition claims.

