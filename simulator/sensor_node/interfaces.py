"""Python hardware-abstraction contracts for simulation and integration tests."""

from __future__ import annotations

from typing import Protocol


class TemperatureSource(Protocol):
    """Logical contract for a temperature source."""

    def read_temperature(self) -> dict[str, object]:
        """Return measured temperature, timestamp, and validity."""


class ClockSource(Protocol):
    def now_seconds(self) -> float:
        """Return monotonic seconds."""


class BatteryMonitor(Protocol):
    def battery_percent(self) -> float:
        """Return battery percentage."""


class RadioTransmitter(Protocol):
    def send(self, packet: bytes) -> bool:
        """Send a packet."""


class LocalStorage(Protocol):
    def store_unsent(self, packet: bytes) -> None:
        """Store an unsent packet."""


class ConfigurationStorage(Protocol):
    def get(self, key: str) -> object:
        """Return a configuration value."""


class DiagnosticLogger(Protocol):
    def info(self, message: str) -> None:
        """Log an info message."""

    def warning(self, message: str) -> None:
        """Log a warning message."""

    def error(self, message: str) -> None:
        """Log an error message."""
