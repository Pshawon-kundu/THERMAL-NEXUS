"""Configuration for the local Thermal Nexus MQTT bridge."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MqttConfig:
    """Runtime MQTT connection settings."""

    host: str = "127.0.0.1"
    port: int = 1883
    keepalive_seconds: int = 60
    client_id: str = "thermal-nexus-ingestion"
    topic_prefix: str = "thermal-nexus/v1"
    username: str = ""
    password: str = ""
    reconnect_min_delay_seconds: float = 1.0
    reconnect_max_delay_seconds: float = 30.0


def load_mqtt_config() -> MqttConfig:
    """Load MQTT config from environment variables without committing secrets."""

    return MqttConfig(
        host=os.getenv("MQTT_HOST", "127.0.0.1"),
        port=int(os.getenv("MQTT_PORT", "1883")),
        keepalive_seconds=int(os.getenv("MQTT_KEEPALIVE_SECONDS", "60")),
        client_id=os.getenv("MQTT_CLIENT_ID", "thermal-nexus-ingestion"),
        topic_prefix=os.getenv("MQTT_TOPIC_PREFIX", "thermal-nexus/v1").rstrip("/"),
        username=os.getenv("MQTT_USERNAME", ""),
        password=os.getenv("MQTT_PASSWORD", ""),
    )
