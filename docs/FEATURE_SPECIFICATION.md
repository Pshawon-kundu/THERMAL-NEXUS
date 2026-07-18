# Feature Specification

Features are generated from current and past `measured_temperature` values only. Future temperatures, future labels, and scenario names are not used as ML input features.

The synthetic ground truth column, `true_temperature`, is used for labels, not for model input features.

## Windows

Configured rolling windows:

- 5 samples
- 10 samples
- 20 samples

## Features

Base features:

- `current_temperature`
- `previous_temperature`
- `temperature_difference`
- `temperature_slope`
- `temperature_acceleration`
- `distance_from_upper_limit`
- `distance_from_lower_limit`
- `distance_from_nearest_limit`
- `time_since_previous_valid_sample`
- `sensor_currently_valid`

Windowed features are suffixed by sample count, such as `_5`, `_10`, and `_20`:

- `rolling_mean`
- `rolling_standard_deviation`
- `rolling_minimum`
- `rolling_maximum`
- `rolling_range`
- `sample_count`
- `valid_sample_count`
- `valid_ratio`
- `maximum_gap_seconds`
- `temperature_slope_ls`

Slope calculations use actual timestamp spacing in seconds.

## Invalid Samples

Invalid and missing sensor values are explicit. They are not silently imputed.

Rows receive:

- `feature_valid`
- `feature_invalid_reason`

Invalid reasons include:

- current sensor sample invalid
- insufficient history
- valid ratio below limit
- excessive time gap
- unsafe numerical calculation

Model training in a future phase should decide whether to filter invalid rows, add missingness indicators, or train policies that can handle partial input. This phase does not train a model.

