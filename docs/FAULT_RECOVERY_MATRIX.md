# Fault Recovery Matrix

| Fault | Detection | Safe Behavior | Evidence |
| --- | --- | --- | --- |
| Missing sensor sample | `sensor_valid=false` or absent measurement | Mark invalid, use sensor-fault fallback interval | Node decision log |
| Invalid sensor sample | Nonfinite or invalid reading | Enter `SENSOR_FAULT` priority state | Node decision log |
| Model artifact unavailable | Runtime load failure | Fall back to configured non-ML safe mode | Runtime log |
| Preprocessing unavailable | Missing preprocessing artifact | Reject model runtime and use fallback | Runtime log |
| Invalid feature value | NaN or infinite feature | Reject inference and mark fallback reason | Node decision log |
| Inference exception | Runtime exception | Enter `MODEL_FAULT` and apply safe intervals | Node decision log |
| CRC failure | Reader CRC validation | Reject packet and store reason | Reader rejected records |
| Unsupported protocol version | Reader protocol check | Reject packet | Reader rejected records |
| Duplicate packet | Sequence registry | Mark duplicate sequence issue | Reader records |
| Missing sequence number | Sequence gap | Mark missing sequence issue | Reader records |
| Out-of-order packet | Sequence registry | Mark out-of-order issue | Reader records |
| Communication outage | Radio outage window | Queue/retry until recovery or exhaustion | Radio events |
| Retry exhaustion | Retry count exceeds limit | Drop packet and record retry count | Radio events |
| Reader restart | Registry storage reload or empty cache | Continue accepting valid packets; later persistence required | Reader records |
| Low battery | Battery estimator below threshold | Apply low-battery policy unless safety states override | Node decision log |

Safety priority is `SENSOR_FAULT`, physical threshold violation,
`EXCURSION_RISK`, `TRANSITION`, `LOW_BATTERY`, then `STABLE`.

