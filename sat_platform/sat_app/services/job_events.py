"""Simple in-memory broker for job progress events."""

from __future__ import annotations

import json
import queue
from typing import Dict, Iterable


class JobEventBroker:
    def __init__(self) -> None:
        self.listeners: set[queue.Queue] = set()

    def publish(self, payload: Dict) -> None:
        message = json.dumps(payload)
        for listener in list(self.listeners):
            try:
                listener.put_nowait(message)
            except queue.Full:
                continue

    def listen(self) -> Iterable[str]:
        q: queue.Queue[str] = queue.Queue()
        self.listeners.add(q)
        try:
            while True:
                data = q.get()
                yield data
        finally:
            self.listeners.discard(q)


job_event_broker = JobEventBroker()

