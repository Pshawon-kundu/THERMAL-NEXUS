"""Reusable MQTT publisher for local Thermal Nexus messages."""

from __future__ import annotations

import json
from collections.abc import Mapping

from host.mqtt.config import MqttConfig, load_mqtt_config
from host.mqtt.topics import node_topic, system_status_topic


class MqttPublisher:
    """Small wrapper around paho-mqtt with injectable clients for tests."""

    def __init__(self, config: MqttConfig | None = None, client: object = None) -> None:
        self.config = config or load_mqtt_config()
        self.client = client or self._make_client()

    def connect(self) -> None:
        """Connect to the configured local broker."""

        if self.config.username:
            self.client.username_pw_set(self.config.username, self.config.password)
        self.client.connect(
            self.config.host, self.config.port, self.config.keepalive_seconds
        )

    def disconnect(self) -> None:
        """Disconnect cleanly."""

        self.client.disconnect()

    def publish_node(
        self, node_id: str, message_type: str, payload: Mapping[str, object]
    ) -> None:
        """Publish a node-scoped JSON payload with QoS 1."""

        topic = node_topic(node_id, message_type, self.config.topic_prefix)
        self.client.publish(topic, json.dumps(dict(payload)), qos=1, retain=False)

    def publish_system_status(self, payload: Mapping[str, object]) -> None:
        """Publish a system status payload with QoS 1."""

        topic = system_status_topic(self.config.topic_prefix)
        self.client.publish(topic, json.dumps(dict(payload)), qos=1, retain=False)

    def _make_client(self) -> object:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "paho-mqtt is not installed. Install dependencies or run "
                "`.venv\\Scripts\\python.exe -m pip install paho-mqtt`."
            ) from exc
        return mqtt.Client(client_id=self.config.client_id)
