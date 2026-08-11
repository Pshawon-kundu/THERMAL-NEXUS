"""Command-line entry point for local MQTT ingestion."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from host.database.connection import DEFAULT_DATABASE_PATH
from host.mqtt.config import load_mqtt_config
from host.mqtt.subscriber import MqttIngestionService


def main(argv: list[str] | None = None) -> int:
    """Run the persistent MQTT ingestion service."""

    parser = argparse.ArgumentParser(description="Run Thermal Nexus MQTT ingestion.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=str(args.log_level).upper())
    service = MqttIngestionService(load_mqtt_config(), args.database)
    service.start_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
