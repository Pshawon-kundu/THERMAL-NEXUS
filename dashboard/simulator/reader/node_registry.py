"""Track reader-side node sequence state."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NodeRegistry:
    """Detect duplicate, missing, and out-of-order sequence numbers."""

    last_sequence_by_node: dict[int, int] = field(default_factory=dict)

    def inspect(self, node_id: int, sequence_number: int) -> list[str]:
        """Return sequence anomalies for one packet."""

        issues: list[str] = []
        previous = self.last_sequence_by_node.get(node_id)
        if previous is not None:
            if sequence_number == previous:
                issues.append("duplicate sequence number")
            elif sequence_number < previous:
                issues.append("out-of-order sequence number")
            elif sequence_number > previous + 1:
                issues.append("missing sequence number")
        if previous is None or sequence_number > previous:
            self.last_sequence_by_node[node_id] = sequence_number
        return issues
