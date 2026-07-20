"""Replay session state machine."""

from __future__ import annotations

from dataclasses import dataclass

from host.replay.models import ReplayEvent


@dataclass
class ReplaySession:
    """Manual deterministic replay controller."""

    events: list[ReplayEvent]
    speed: float = 1.0
    position: int = 0
    running: bool = False

    def start(self) -> None:
        self.running = True
        self.position = 0

    def pause(self) -> None:
        self.running = False

    def resume(self) -> None:
        self.running = True

    def restart(self) -> None:
        self.position = 0
        self.running = False

    def step_forward(self) -> ReplayEvent | None:
        if not self.events:
            return None
        self.position = min(len(self.events) - 1, self.position + 1)
        return self.current_event

    def step_backward(self) -> ReplayEvent | None:
        if not self.events:
            return None
        self.position = max(0, self.position - 1)
        return self.current_event

    def jump_to_timestamp(self, timestamp: float) -> ReplayEvent | None:
        for index, event in enumerate(self.events):
            if event.timestamp >= timestamp:
                self.position = index
                return event
        self.position = max(0, len(self.events) - 1)
        return self.current_event

    def jump_to_next(self, prefix: str) -> ReplayEvent | None:
        for index in range(self.position + 1, len(self.events)):
            if self.events[index].event_type.startswith(prefix):
                self.position = index
                return self.events[index]
        return None

    def filter_events(self, event_types: set[str]) -> list[ReplayEvent]:
        return [event for event in self.events if event.event_type in event_types]

    @property
    def current_event(self) -> ReplayEvent | None:
        if not self.events:
            return None
        return self.events[self.position]

    @property
    def records_until_current(self) -> list[ReplayEvent]:
        return self.events[: self.position + 1]
