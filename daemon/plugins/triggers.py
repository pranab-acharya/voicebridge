r"""
Keyword / regex trigger system.

Usage:
    plugin = TriggerPlugin()
    plugin.add(KeywordTrigger("salary",    [r"\$[\d,]+", r"compensation"]))
    plugin.add(KeywordTrigger("timeline",  [r"start date", r"notice period"]))
    plugin.add(KeywordTrigger("next_step", [r"next steps", r"follow.?up"]))
    plugin.register(bus)

When a transcript contains a match the plugin publishes 'trigger_fired'
with keys: trigger, matched_text, full_text.

Add your own triggers at runtime:
    plugin.add(KeywordTrigger("remote", [r"remote", r"work from home"]))
"""
import re
from typing import List, Optional
from .base import Plugin


class KeywordTrigger:
    def __init__(self, name: str, patterns: List[str],
                 case_sensitive: bool = False) -> None:
        self.name = name
        flags = 0 if case_sensitive else re.IGNORECASE
        self._re = [re.compile(p, flags) for p in patterns]

    def check(self, text: str) -> Optional[str]:
        for pattern in self._re:
            m = pattern.search(text)
            if m:
                return m.group(0)
        return None


class TriggerPlugin(Plugin):
    name = "triggers"

    def __init__(self) -> None:
        self._triggers: List[KeywordTrigger] = []

    def add(self, trigger: KeywordTrigger) -> None:
        self._triggers.append(trigger)

    def on_transcript(self, data: dict) -> None:
        text = data.get("text", "")
        for t in self._triggers:
            match = t.check(text)
            if match:
                self._bus.publish("trigger_fired", {
                    "trigger":      t.name,
                    "matched_text": match,
                    "full_text":    text,
                })
