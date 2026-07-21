# STM32 Integration Preparation

This folder contains hardware-independent preparation templates for a future
STM32U585 implementation. It does not include STM32 HAL calls or physical driver
implementations.

Runtime flow:

1. Read TMP117 sample.
2. Update history buffer.
3. Extract features.
4. Apply preprocessing.
5. Run model.
6. Apply adaptive policy.
7. Create protocol packet.
8. Request XBee transmission.
9. Store unsent packet.
10. Record diagnostics.
