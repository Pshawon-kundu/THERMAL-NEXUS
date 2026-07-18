# Runtime Operating Mode Report

All values are software simulation results. Energy values are ESTIMATED SOFTWARE VALUE, not measured Wh.

| mode | total_sensor_samples | total_transmissions | delivered_packets | lost_packets | corrupted_packets | retry_count | first_warning_time_seconds | warning_lead_time_seconds | missed_excursion_events | false_alert_events | time_spent_in_each_state | number_of_state_transitions | reader_records | alerts | estimated_sensing_energy | estimated_inference_energy | estimated_transmission_energy | estimated_total_energy | energy_label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed | 121 | 56 | 56 | 3 | 0 | 4 | 4920.0 | 0.0 | 0 | 0 | {'STABLE': 82, 'EXCURSION_RISK': 39} | 1 | 56 | 40 | 0.242 | 0.0 | 0.56 | 0.802 | ESTIMATED SOFTWARE VALUE |
| rule_based | 121 | 82 | 82 | 5 | 0 | 7 | 480.0 | 4440.0 | 0 | 0 | {'EXCURSION_RISK': 62, 'STABLE': 42, 'TRANSITION': 13, 'MODEL_FAULT': 4} | 28 | 82 | 62 | 0.242 | 0.0 | 0.8200000000000001 | 1.062 | ESTIMATED SOFTWARE VALUE |
| ml | 121 | 107 | 107 | 8 | 0 | 11 | 4320.0 | 600.0 | 0 | 0 | {'TRANSITION': 51, 'EXCURSION_RISK': 49, 'STABLE': 17, 'MODEL_FAULT': 4} | 3 | 107 | 49 | 0.242 | 0.121 | 1.07 | 1.433 | ESTIMATED SOFTWARE VALUE |