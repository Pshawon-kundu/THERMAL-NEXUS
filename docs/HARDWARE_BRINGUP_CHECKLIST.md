# Hardware Bring-Up Checklist

- Confirm TMP117 wiring, address, conversion rate, and calibration record.
- Verify STM32U585 clock source and timestamp monotonicity.
- Validate battery measurement scaling and low-battery thresholds.
- Confirm nonvolatile storage behavior during reset and link outage.
- Verify protocol v1 packet bytes against golden vectors.
- Validate XBee configuration, addressing, retries, and link recovery.
- Compare reader CRC rejection against intentionally corrupted packets.
- Collect reference temperature data when possible.
- Import real data through the ingestion contract before labeling.
- Retrain or revalidate models with real TMP117 runs before hardware claims.

Do not report physical accuracy, range, battery life, or energy results until
they are measured on the final hardware setup.

