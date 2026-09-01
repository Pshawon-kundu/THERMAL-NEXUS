# Energy Policy Comparison

Disclaimer: All numbers are software-estimated values from synthetic scenarios. Real hardware measurements should replace these before any claim is made about deployed performance.

**Interpretation:** ML is a predictive system: it uses MORE packets during active events (earlier warning lead time) and the SAME or FEWER packets during stable periods. The aggregate cost is the price of predictive alerting; per-scenario breakdown is provided for transparency.

## Aggregate per-mode totals

| mode | packets | delivered | missed_excursions | false_positives | median_lead_seconds | energy_units |
|------|---------|-----------|-------------------|-----------------|----------------------|--------------|
| fixed | 128 | 128 | 0 | 0 | 0 | 2.732 |
| ml | 193 | 193 | 0 | 4 | 0 | 4.108 |
| rule_based | 154 | 154 | 0 | 78 | 1740 | 2.992 |

## Per-scenario packet counts

| scenario | fixed | rule_based | ml |
|----------|-------|------------|-----|
| gradual_warming | 21 | 24 | 46 |
| repeated_door_opening | 21 | 32 | 36 |
| short_door_opening | 24 | 30 | 31 |
| stable_cold | 25 | 26 | 31 |
| stable_room | 13 | 13 | 13 |
| sudden_spike | 24 | 29 | 36 |

## Comparison vs fixed baseline

- ML packets: 193.0
- Fixed packets: 128.0
- ML minus fixed: +65 packets
- ML recall estimate: 1.000 (target 0.9)

_Chart: `evidence/ai/energy_policy_figure.png`_