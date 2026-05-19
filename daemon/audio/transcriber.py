"""
Streaming Whisper transcription.

Audio is accumulated in a sliding window (default 10 s).
Every STEP_SEC seconds a transcription pass runs in a background thread
and emits the result via the on_transcript callback.
"""
import threading
import time
from collections import deque
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 16_000
WINDOW_SEC  = 10.0   # keep this much audio in memory
STEP_SEC    = 2.0    # transcribe every N seconds
MIN_SEC     = 1.0    # don't attempt before this much audio is buffered


class StreamingTranscriber:
    def __init__(self,
                 model_size:     str = "base",
                 device:         str = "cpu",
                 on_transcript:  Callable[[str], None] | None = None) -> None:
        from faster_whisper import WhisperModel
        self._model        = WhisperModel(model_size, device=device, compute_type="int8")
        self._on_transcript = on_transcript
        self._buf: deque   = deque()
        self._buf_dur      = 0.0          # seconds of audio in buf
        self._last_text    = ""
        self._running      = False
        self._lock         = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, name="Transcriber", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
            self._buf_dur  = 0.0
            self._last_text = ""

    # ── audio ingestion ──────────────────────────────────────────────────────

    def push(self, pcm: np.ndarray) -> None:
        """Append a float32 PCM frame to the sliding window."""
        dur = len(pcm) / SAMPLE_RATE
        with self._lock:
            self._buf.append(pcm)
            self._buf_dur += dur
            # Trim oldest frames when window is full
            while self._buf_dur > WINDOW_SEC and self._buf:
                old = self._buf.popleft()
                self._buf_dur -= len(old) / SAMPLE_RATE

    # ── inference loop ───────────────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            time.sleep(STEP_SEC)
            if not self._running:
                break

            with self._lock:
                if self._buf_dur < MIN_SEC:
                    continue
                audio = np.concatenate(list(self._buf))

            try:
                segments, _ = self._model.transcribe(
                    audio,
                    language="en",
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 400},
                )
                text = " ".join(s.text.strip() for s in segments).strip()
                if text and text != self._last_text:
                    self._last_text = text
                    if self._on_transcript:
                        self._on_transcript(text)
            except Exception:
                pass
