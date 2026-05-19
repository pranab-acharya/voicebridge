"""
Writes per-call transcript logs to a directory.

File format: logs/call_YYYYMMDD_HHMMSS_<number>.txt
Each line: [HH:MM:SS] <text>
Trigger hits are marked with *** TRIGGER: <name> ***.
"""
import os
from datetime import datetime
from typing import Optional, TextIO
from .base import Plugin


class TranscriptLogPlugin(Plugin):
    name = "transcript_log"

    def __init__(self, log_dir: str = "logs") -> None:
        self._log_dir = log_dir
        self._file: Optional[TextIO] = None

    def on_call_start(self, data: dict) -> None:
        os.makedirs(self._log_dir, exist_ok=True)
        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        number = (data.get("number") or "unknown").replace("+", "").replace(" ", "")
        path   = os.path.join(self._log_dir, f"call_{ts}_{number}.txt")
        self._file = open(path, "w", encoding="utf-8")
        self._write(f"Call start : {datetime.now().isoformat()}")
        self._write(f"Number     : {data.get('number', 'unknown')}\n")

    def on_transcript(self, data: dict) -> None:
        self._write(data.get("text", ""))

    def on_trigger_fired(self, data: dict) -> None:
        self._write(
            f"*** TRIGGER: {data.get('trigger')} ***  \"{data.get('matched_text')}\""
        )

    def on_call_end(self, data: dict) -> None:
        dur = data.get("duration_s")
        if dur:
            self._write(f"\nCall end   : {datetime.now().isoformat()}  ({dur:.0f}s)")
        if self._file:
            self._file.close()
            self._file = None

    def _write(self, text: str) -> None:
        if self._file:
            ts = datetime.now().strftime("%H:%M:%S")
            self._file.write(f"[{ts}] {text}\n")
            self._file.flush()
