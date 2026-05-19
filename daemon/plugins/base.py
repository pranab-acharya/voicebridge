"""
Plugin base class.

Subclasses define on_<event_name>(self, data: dict) methods.
Calling plugin.register(bus) auto-subscribes all of them.

Extensibility: drop a new .py in plugins/, subclass Plugin,
add it to the daemon's plugin list in voicebridge.py.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.event_bus import EventBus


class Plugin:
    name: str = "unnamed"

    def register(self, bus: "EventBus") -> None:
        self._bus = bus
        for attr in dir(self):
            if attr.startswith("on_") and callable(getattr(self, attr)):
                bus.subscribe(attr[3:], getattr(self, attr))

    def unregister(self, bus: "EventBus") -> None:
        for attr in dir(self):
            if attr.startswith("on_") and callable(getattr(self, attr)):
                bus.unsubscribe(attr[3:], getattr(self, attr))
