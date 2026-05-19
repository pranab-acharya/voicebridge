"""Opus → PCM float32 decoder."""
import numpy as np
from typing import Optional

SAMPLE_RATE  = 16_000
CHANNELS     = 1
FRAME_SIZE   = 320  # 20 ms at 16 kHz


class OpusDecoder:
    def __init__(self) -> None:
        import opuslib
        self._dec = opuslib.Decoder(SAMPLE_RATE, CHANNELS)

    def decode(self, opus_data: bytes) -> Optional[np.ndarray]:
        """Return float32 PCM array in [-1, 1] or None on error."""
        try:
            pcm_bytes = self._dec.decode(opus_data, FRAME_SIZE)
            pcm_i16   = np.frombuffer(pcm_bytes, dtype=np.int16)
            return pcm_i16.astype(np.float32) / 32_768.0
        except Exception:
            return None
