"""Opt-in development telemetry for progression and story diagnostics."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
import json
import os

from gameplay.events import AccessDenied, DialogueSelected, ProgressionUpdated, QuestStateChanged


class DevelopmentTelemetry:
    """Keep a bounded structured trace; optionally mirror it as JSON lines."""

    def __init__(self, enabled=False, *, capacity=500, sink=None):
        self.enabled = bool(enabled)
        self.records = deque(maxlen=max(1, int(capacity)))
        self.sink = sink
        self._unsubscribes = []

    @classmethod
    def from_environment(cls):
        value = os.environ.get("OCEANS_APART_TELEMETRY", "").strip().lower()
        return cls(value in {"1", "true", "yes", "on"})

    def bind(self, dispatcher):
        self.close()
        for event_type in (ProgressionUpdated, QuestStateChanged, DialogueSelected, AccessDenied):
            self._unsubscribes.append(dispatcher.subscribe(event_type, self.record_event))
        return self

    def record_event(self, event):
        return self.record(type(event).__name__, **asdict(event))

    def record(self, category, **fields):
        if not self.enabled:
            return None
        record = {"category": str(category), **fields}
        self.records.append(record)
        if self.sink is not None:
            self.sink(json.dumps(record, sort_keys=True))
        return record

    def snapshot(self):
        return tuple(dict(record) for record in self.records)

    def close(self):
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes = []
