# STM32 Integration Guide

The STM32 preparation files are interface templates only. They are not physical
firmware and have not been validated on STM32U585 hardware.

Integration entry points:

- `embedded/interfaces/temperature_source.h`
- `embedded/interfaces/clock_source.h`
- `embedded/interfaces/battery_source.h`
- `embedded/interfaces/radio_transport.h`
- `embedded/interfaces/storage_backend.h`
- `embedded/interfaces/diagnostic_logger.h`
- `embedded/stm32_integration/app_runtime.c`

Hardware bring-up must replace simulator adapters with TMP117, STM32 clock,
battery monitor, nonvolatile storage, diagnostic logging, and XBee transport
implementations. Each replacement must preserve units, bounds, error codes, and
safe fallback behavior defined by the software simulator.

