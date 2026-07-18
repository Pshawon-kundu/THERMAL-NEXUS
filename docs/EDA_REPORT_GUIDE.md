# EDA Report Guide

EDA outputs are generated under `evidence/eda/`.

The dataset health report summarizes rows, runs, scenarios, target classes, invalid rows, missing values, feature ranges, duplicated data, constant features, highly correlated features, infinite values, and NaN-bearing feature columns.

Plots are saved under `evidence/eda/plots/`.

Training data is used for exploratory plots that could influence thresholds or model design. Validation and test splits are used only for integrity checks such as class distribution and run leakage.

Synthetic EDA is a prototype diagnostic only. It must be rerun on real TMP117 datasets before making hardware or competition claims.

