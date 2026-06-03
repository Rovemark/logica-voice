"""
audio_filter.py — input audio filtering (noise suppression) before VAD/STT.

A NoiseFilterProcessor cleans the incoming mic audio so VAD and STT see speech, not
room hum / keyboard / fan. Pluggable backend:
  - 'noisereduce' (spectral gating, pure-python, no native deps) — default if installed
  - 'rnnoise'     (RNNoise via the `rnnoise` package, if available)
  - 'none'        passthrough

Place it FIRST in the pipeline (before VAD). Operates on AudioInFrame in place.
"""

import os
import numpy as np

from .processor import FrameProcessor, Direction
from .frames import AudioInFrame

FILTER_BACKEND = os.environ.get('LVP_NOISE_FILTER', 'auto')  # auto|noisereduce|rnnoise|none


class NoiseFilterProcessor(FrameProcessor):
    def __init__(self, backend=FILTER_BACKEND, name=None):
        super().__init__(name)
        self.backend = backend
        self._fn = self._resolve_backend(backend)

    def _resolve_backend(self, backend):
        if backend in ('none',):
            return None
        if backend in ('auto', 'noisereduce'):
            try:
                import noisereduce as nr  # noqa
                print('[noise] backend=noisereduce', flush=True)
                return self._noisereduce
            except ImportError:
                if backend == 'noisereduce':
                    print('[noise] noisereduce not installed — passthrough', flush=True)
        if backend in ('auto', 'rnnoise'):
            try:
                import rnnoise  # noqa
                print('[noise] backend=rnnoise', flush=True)
                return self._rnnoise
            except ImportError:
                if backend == 'rnnoise':
                    print('[noise] rnnoise not installed — passthrough', flush=True)
        if backend == 'auto':
            print('[noise] no backend available — passthrough', flush=True)
        return None

    def _noisereduce(self, pcm_i16, sr):
        import noisereduce as nr
        f = pcm_i16.astype(np.float32) / 32768.0
        out = nr.reduce_noise(y=f, sr=sr, stationary=True)
        return np.clip(out * 32768.0, -32768, 32767).astype(np.int16)

    def _rnnoise(self, pcm_i16, sr):
        # rnnoise operates at 48k frames of 480 samples; many wrappers handle resampling.
        import rnnoise
        den = rnnoise.RNNoise()
        return den.process(pcm_i16)

    async def process_frame(self, frame, direction):
        if isinstance(frame, AudioInFrame) and self._fn is not None and frame.pcm:
            try:
                pcm = np.frombuffer(frame.pcm, dtype=np.int16)
                cleaned = self._fn(pcm, frame.sample_rate)
                frame = AudioInFrame(pcm=cleaned.tobytes(), sample_rate=frame.sample_rate)
            except Exception as e:
                print(f'[noise] filter failed, passthrough: {e}', flush=True)
        await super().process_frame(frame, direction)
