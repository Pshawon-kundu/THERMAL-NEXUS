# External T15 Benchmark Report

Dataset label: `EXTERNAL_DERIVED_BENCHMARK`

This benchmark is separate from the synthetic cold-chain model pipeline.
The locked test split is evaluated only from the external T15 model-ready files.

## Model-Ready Datasets

- temperature_only: 3321 rows
- multivariate: 3321 rows

## Locked Test Baselines

| dataset | name | model | horizon_minutes | split | mae_c | rmse_c | rows |
| --- | --- | --- | --- | --- | --- | --- | --- |
| temperature_only | historical_mean_30m | historical_mean | 30 | test | 3.175175701024261 | 3.581191607991931 | 551 |
| temperature_only | historical_mean_60m | historical_mean | 60 | test | 3.226381844504245 | 3.6657059321579353 | 551 |
| temperature_only | historical_mean_90m | historical_mean | 90 | test | 3.277665244383253 | 3.764302272735758 | 551 |
| temperature_only | linear_trend_30m | linear_trend | 30 | test | 0.0701661222020568 | 0.0950134054497804 | 551 |
| temperature_only | linear_trend_60m | linear_trend | 60 | test | 0.1693802782819116 | 0.2287693244630611 | 551 |
| temperature_only | linear_trend_90m | linear_trend | 90 | test | 0.3026539019963702 | 0.4041137400986005 | 551 |
| temperature_only | persistence_30m | persistence | 30 | test | 0.2369651542649727 | 0.2759801571025307 | 551 |
| temperature_only | persistence_60m | persistence | 60 | test | 0.4715698729582577 | 0.5489075890739832 | 551 |
| temperature_only | persistence_90m | persistence | 90 | test | 0.7020695099818512 | 0.8178729551922143 | 551 |

## Locked Test Regression Models

| dataset | name | model | horizon_minutes | split | mae_c | rmse_c | rows |
| --- | --- | --- | --- | --- | --- | --- | --- |
| multivariate | ridge_30m | ridge | 30 | test | 0.0322943115721733 | 0.043543924475048 | 551 |
| multivariate | ridge_60m | ridge | 60 | test | 0.0697051638837156 | 0.0951473545685676 | 551 |
| multivariate | ridge_90m | ridge | 90 | test | 0.1149567156603679 | 0.1564713504153671 | 551 |
| multivariate | small_forest_30m | small_forest | 30 | test | 0.2486472067862271 | 0.5257793469894275 | 551 |
| multivariate | small_forest_60m | small_forest | 60 | test | 0.3572366634275781 | 0.6328991012118177 | 551 |
| multivariate | small_forest_90m | small_forest | 90 | test | 0.465320595726945 | 0.7443473961907028 | 551 |
| multivariate | small_tree_30m | small_tree | 30 | test | 0.3854102083131011 | 0.6348066606066228 | 551 |
| multivariate | small_tree_60m | small_tree | 60 | test | 0.5087101170205983 | 0.7607275629931809 | 551 |
| multivariate | small_tree_90m | small_tree | 90 | test | 0.6228139132712087 | 0.8899506476331357 | 551 |
| temperature_only | ridge_30m | ridge | 30 | test | 0.0358251514190446 | 0.0471686723044176 | 551 |
| temperature_only | ridge_60m | ridge | 60 | test | 0.0820050718491854 | 0.1074213759265707 | 551 |
| temperature_only | ridge_90m | ridge | 90 | test | 0.1402788581985902 | 0.1815327498518586 | 551 |
| temperature_only | small_forest_30m | small_forest | 30 | test | 0.2483703393129901 | 0.5238127199622774 | 551 |
| temperature_only | small_forest_60m | small_forest | 60 | test | 0.3694031272774622 | 0.6446703085175782 | 551 |
| temperature_only | small_forest_90m | small_forest | 90 | test | 0.4723674693347073 | 0.74685523231649 | 551 |
| temperature_only | small_tree_30m | small_tree | 30 | test | 0.388462753896228 | 0.6361362608938146 | 551 |
| temperature_only | small_tree_60m | small_tree | 60 | test | 0.503896544886151 | 0.7617321275241232 | 551 |
| temperature_only | small_tree_90m | small_tree | 90 | test | 0.614462222795725 | 0.8767963167425536 | 551 |

## Locked Test Classification Models

| dataset | model | split | accuracy | macro_f1 | rows |
| --- | --- | --- | --- | --- | --- |
| multivariate | logistic_regression | test | 0.8911070780399274 | 0.83849723385554 | 551 |
| multivariate | small_forest | test | 0.8548094373865699 | 0.6778921778921779 | 551 |
| multivariate | small_tree | test | 0.8493647912885662 | 0.7743574622831589 | 551 |
| temperature_only | logistic_regression | test | 0.852994555353902 | 0.8004039828462913 | 551 |
| temperature_only | small_forest | test | 0.8475499092558983 | 0.6713798547891977 | 551 |
| temperature_only | small_tree | test | 0.8638838475499092 | 0.798927088523501 | 551 |

## Plots

- `plots/test_regression_mae.png`
- `plots/test_classification_macro_f1.png`

## Limitations

- External T15 is building-environment data, not cold-chain data.
- Future-temperature targets are derived from later samples in the same series.
- The multivariate dataset is a research reference and not the primary deployable benchmark.
