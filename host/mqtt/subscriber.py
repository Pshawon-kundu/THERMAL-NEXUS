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
MQTT_SUCCESS = 0


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
        self.database_path = database_path.resolve()
        self.store = store or MqttSqliteStore(database_path)
        self.client = client or self._make_client()
        self._stopping = False
        self._configure_client()

    def start_forever(self) -> None:
        """Connect once, run the network loop, and reconnect only after failures."""

        delay = self.config.reconnect_min_delay_seconds
        LOGGER.info("[DB] ingestion database=%s", self.database_path)
        self._connect_with_retry(delay)
        delay = self.config.reconnect_min_delay_seconds

        while True:
            try:
                result = self.client.loop(timeout=1.0)
                if result in (None, MQTT_SUCCESS):
                    delay = self.config.reconnect_min_delay_seconds
                    continue
                LOGGER.warning("[MQTT] Disconnected reason=%s", result)
                delay = self._reconnect_after_delay(delay)
            except KeyboardInterrupt:
                self.stop()
                return
            except OSError as exc:
                LOGGER.warning("[MQTT] Disconnected reason=%s", exc)
                delay = self._reconnect_after_delay(delay)

    def stop(self) -> None:
        """Disconnect the MQTT client cleanly."""

        self._stopping = True
        self.client.disconnect()

    def _connect_with_retry(self, delay: float) -> None:
        while True:
            try:
                LOGGER.info(
                    "[MQTT] Connecting to %s:%s", self.config.host, self.config.port
                )
                self.client.connect(
                    self.config.host,
                    self.config.port,
                    self.config.keepalive_seconds,
                )
                return
            except KeyboardInterrupt:
                self.stop()
                raise
            except OSError as exc:
                LOGGER.warning("[MQTT] Connection failed reason=%s", exc)
                LOGGER.info("[MQTT] Reconnecting in %.1fs", delay)
                time.sleep(delay)
                delay = min(delay * 2.0, self.config.reconnect_max_delay_seconds)

    def _reconnect_after_delay(self, delay: float) -> float:
        LOGGER.info("[MQTT] Reconnecting in %.1fs", delay)
        time.sleep(delay)
        try:
            if hasattr(self.client, "reconnect"):
                self.client.reconnect()
            else:
                self.client.connect(
                    self.config.host,
                    self.config.port,
                    self.config.keepalive_seconds,
                )
            return self.config.reconnect_min_delay_seconds
        except OSError as exc:
            LOGGER.warning("[MQTT] Reconnect failed reason=%s", exc)
            return min(delay * 2.0, self.config.reconnect_max_delay_seconds)

    def _configure_client(self) -> None:
        if self.config.username:
            self.client.username_pw_set(self.config.username, self.config.password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(
            min_delay=int(self.config.reconnect_min_delay_seconds),
            max_delay=int(self.config.reconnect_max_delay_seconds),
        )

    def _on_connect(
        self, client: object, _userdata: object, _flags: object, rc: int
    ) -> None:
        if rc != 0:
            LOGGER.warning("[MQTT] Connection failed reason=%s", rc)
            return
        LOGGER.info("[MQTT] Connected")
        for topic_filter, qos in subscription_filters(self.config):
            client.subscribe(topic_filter, qos=qos)
        LOGGER.info("[MQTT] Subscribed to Thermal Nexus MQTT topics")

    def _on_disconnect(self, _client: object, _userdata: object, *args: object) -> None:
        reason = args[-1] if args else "unknown"
        if self._stopping:
            return
        LOGGER.warning("[MQTT] Disconnected reason=%s", reason)

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
                result = self.store.store_telemetry(message)
                LOGGER.info(
                    "[MQTT] received node=%s seq=%s",
                    message.node_id,
                    message.sequence_number,
                )
                status = "duplicate" if result.duplicate else "inserted"
                LOGGER.info(
                    "[DB] %s telemetry node=%s seq=%s",
                    status,
                    message.node_id,
                    message.sequence_number,
                )
            elif isinstance(message, DecisionMessage):
                result = self.store.store_decision(message)
                status = "duplicate" if result.duplicate else "inserted"
                LOGGER.info(
                    "[DB] %s decision node=%s seq=%s",
                    status,
                    message.node_id,
                    message.sequence_number,
                )
            elif isinstance(message, AlertMessage):
                result = self.store.store_alert(message)
                status = "duplicate" if result.duplicate else "inserted"
                LOGGER.info(
                    "[DB] %s alert node=%s seq=%s",
                    status,
                    message.node_id,
                    message.sequence_number,
                )
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
