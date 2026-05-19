from datetime import datetime
from typing import Optional


class CallSession:
    def __init__(self) -> None:
        self._active = False
        self._number = ""
        self._started: Optional[datetime] = None
        self.frames_received = 0
        self.bytes_received  = 0

    def start(self, number: str) -> None:
        self._active        = True
        self._number        = number
        self._started       = datetime.now()
        self.frames_received = 0
        self.bytes_received  = 0

    def end(self) -> None:
        self._active  = False
        self._number  = ""
        self._started = None

    def record_frame(self, byte_count: int) -> None:
        self.frames_received += 1
        self.bytes_received  += byte_count

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def number(self) -> str:
        return self._number

    @property
    def duration_s(self) -> Optional[float]:
        return (datetime.now() - self._started).total_seconds() if self._started else None
