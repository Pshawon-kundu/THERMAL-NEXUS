"""Versioned MQTT topic helpers."""

from __future__ import annotations

from dataclasses import dataclass

from host.mqtt.config import MqttConfig

NODE_MESSAGE_TYPES = {"telemetry", "decision", "status", "alert", "command"}


@dataclass(frozen=True)
class ParsedTopic:
    """Parsed Thermal Nexus MQTT topic."""

    node_id: str | None
    message_type: str
    is_system: bool = False


def node_topic(
    node_id: str, message_type: str, prefix: str = "thermal-nexus/v1"
) -> str:
    """Build a node-scoped MQTT topic."""

    normalized = _non_empty(node_id, "node_id")
    if message_type not in NODE_MESSAGE_TYPES:
        raise ValueError(f"Unsupported node MQTT message type: {message_type}")
    return f"{prefix.rstrip('/')}/nodes/{normalized}/{message_type}"


def system_status_topic(prefix: str = "thermal-nexus/v1") -> str:
    """Build the system status topic."""

    return f"{prefix.rstrip('/')}/system/status"


def subscription_filters(config: MqttConfig) -> list[tuple[str, int]]:
    """Return QoS 1 subscriptions for required local topics."""

    prefix = config.topic_prefix
    return [
        (f"{prefix}/nodes/+/telemetry", 1),
        (f"{prefix}/nodes/+/decision", 1),
        (f"{prefix}/nodes/+/status", 1),
        (f"{prefix}/nodes/+/alert", 1),
        (f"{prefix}/system/status", 1),
    ]


def parse_topic(topic: str, prefix: str = "thermal-nexus/v1") -> ParsedTopic:
    """Parse and validate a Thermal Nexus MQTT topic."""

    expected_prefix = prefix.rstrip("/")
    if not topic.startswith(expected_prefix + "/"):
        raise ValueError(f"Topic outside Thermal Nexus prefix: {topic}")
    tail = topic[len(expected_prefix) + 1 :].split("/")
    if tail == ["system", "status"]:
        return ParsedTopic(node_id=None, message_type="status", is_system=True)
    if len(tail) != 3 or tail[0] != "nodes":
        raise ValueError(f"Malformed Thermal Nexus topic: {topic}")
    node_id = _non_empty(tail[1], "node_id")
    message_type = tail[2]
    if message_type not in NODE_MESSAGE_TYPES:
        raise ValueError(f"Unsupported node MQTT message type: {message_type}")
    return ParsedTopic(node_id=node_id, message_type=message_type)


def _non_empty(value: str, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} must be non-empty")
    if "/" in normalized or "+" in normalized or "#" in normalized:
        raise ValueError(f"{label} contains MQTT wildcard/path characters")
    return normalized
