"""MQTT subscriber callbacks for local ingestion into SQLite."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from host.database.connection import DEFAULT_DATABASE_PATH
from host.mqtt.config import MqttConfig, load_mqtt_config
from host.mqtt.schemas import (
    AlertMessage,
    DecisionMessage,
    MqttValidationError,
    TelemetryMessage,
    validate_payload,
)
from host.mqtt.storage import MqttSqliteStore
from host.mqtt.topics import parse_topic, subscription_filters

LOGGER = logging.getLogger(__name__)


class MqttIngestionService:
    """Persistent MQTT-to-SQLite ingestion service."""

    def __init__(
        self,
        config: MqttConfig | None = None,
        database_path: Path = DEFAULT_DATABASE_PATH,
        client: object = None,
        store: MqttSqliteStore | None = None,
    ) -> None:
        self.config = config or load_mqtt_config()
        self.store = store or MqttSqliteStore(database_path)
        self.client = client or self._make_client()
        self._configure_client()

    def start_forever(self) -> None:
        """Connect and run until interrupted, using bounded reconnect backoff."""

        delay = self.config.reconnect_min_delay_seconds
        while True:
            try:
                self.client.connect(
                    self.config.host,
                    self.config.port,
                    self.config.keepalive_seconds,
                )
                self.client.loop_forever(retry_first_connection=True)
                delay = self.config.reconnect_min_delay_seconds
            except KeyboardInterrupt:
                self.stop()
                return
            except OSError as exc:
                LOGGER.warning("MQTT broker unavailable: %s", exc)
                time.sleep(delay)
                delay = min(delay * 2.0, self.config.reconnect_max_delay_seconds)

    def stop(self) -> None:
        """Disconnect the MQTT client cleanly."""

        self.client.disconnect()

    def _configure_client(self) -> None:
        if self.config.username:
            self.client.username_pw_set(self.config.username, self.config.password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(
            min_delay=int(self.config.reconnect_min_delay_seconds),
            max_delay=int(self.config.reconnect_max_delay_seconds),
        )

    def _on_connect(
        self, client: object, _userdata: object, _flags: object, rc: int
    ) -> None:
        if rc != 0:
            LOGGER.warning("MQTT connection returned rc=%s", rc)
            return
        for topic_filter, qos in subscription_filters(self.config):
            client.subscribe(topic_filter, qos=qos)
        LOGGER.info("Subscribed to Thermal Nexus MQTT topics")

    def _on_message(self, _client: object, _userdata: object, msg: object) -> None:
        topic = str(getattr(msg, "topic", ""))
        payload = getattr(msg, "payload", b"")
        try:
            parsed = parse_topic(topic, self.config.topic_prefix)
            if parsed.is_system:
                LOGGER.info("System status received: %s", payload)
                return
            message = validate_payload(payload, parsed.message_type)
            if parsed.node_id != message.node_id:
                raise MqttValidationError("node_id mismatch between topic and payload")
            if isinstance(message, TelemetryMessage):
                self.store.store_telemetry(message)
            elif isinstance(message, DecisionMessage):
                self.store.store_decision(message)
            elif isinstance(message, AlertMessage):
                self.store.store_alert(message)
        except Exception as exc:
            LOGGER.warning("Rejected MQTT message on %s: %s", topic, exc)

    def _make_client(self) -> object:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "paho-mqtt is not installed. Install dependencies or run "
                "`.venv\\Scripts\\python.exe -m pip install paho-mqtt`."
            ) from exc
        return mqtt.Client(client_id=self.config.client_id)
