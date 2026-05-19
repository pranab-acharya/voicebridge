"""
Simple synchronous event bus.

Plugins subscribe by calling bus.subscribe("event_name", handler).
The daemon publishes by calling bus.publish("event_name", {data}).
"""
from collections import defaultdict
from typing import Callable, Dict, List, Any


class EventBus:
    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable[[dict], None]) -> None:
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable) -> None:
        try:
            self._handlers[event].remove(handler)
        except ValueError:
            pass

    def publish(self, event: str, data: dict | None = None) -> None:
        for handler in list(self._handlers[event]):
            try:
                handler(data or {})
            except Exception as exc:
                print(f"[EventBus] handler error on '{event}': {exc}")
