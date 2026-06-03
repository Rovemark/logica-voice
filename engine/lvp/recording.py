"""
recording.py — record the conversation (user + bot) for debug/audit/dataset.

AudioBufferProcessor buffers user audio (AudioInFrame, 16 kHz) and bot audio
(AudioOutFrame, 24 kHz), resampling user up to 24 kHz, and writes a stereo WAV
(user = left, bot = right) on demand. Great for debugging latency/quality, auditing,
or building a PT-BR dataset to fine-tune your own VAD/turn models.

    rec = AudioBufferProcessor()
    # ... place anywhere in the pipeline (it observes audio both ways) ...
    rec.save_wav('/tmp/conversation.wav')   # stereo: L=user, R=bot
"""

import io
import wave
import numpy as np

from .processor import FrameProcessor, Direction
from .frames import AudioInFrame, AudioOutFrame, EndFrame

_SR = 24000  # common output rate


def _resample_to_24k(pcm_i16: np.ndarray, src_sr: int) -> np.ndarray:
    if src_sr == _SR:
        return pcm_i16
    ratio = _SR / src_sr
    idx = np.minimum((np.arange(int(len(pcm_i16) * ratio)) / ratio).astype(np.int64),
                     len(pcm_i16) - 1)
    return pcm_i16[idx]


class AudioBufferProcessor(FrameProcessor):
    def __init__(self, on_save=None, name=None):
        super().__init__(name)
        self.on_save = on_save
        self._user = []   # list of int16 arrays @ 24k
        self._bot = []

    async def process_frame(self, frame, direction):
        if isinstance(frame, AudioInFrame) and frame.pcm:
            pcm = np.frombuffer(frame.pcm, dtype=np.int16)
            self._user.append(_resample_to_24k(pcm, frame.sample_rate))
        elif isinstance(frame, AudioOutFrame) and frame.pcm:
            pcm = np.frombuffer(frame.pcm, dtype=np.int16)
            self._bot.append(_resample_to_24k(pcm, frame.sample_rate))
        elif isinstance(frame, EndFrame) and self.on_save:
            try:
                self.on_save(self.to_wav_bytes())
            except Exception:
                pass
        await super().process_frame(frame, direction)

    def _stereo(self):
        u = np.concatenate(self._user) if self._user else np.zeros(0, dtype=np.int16)
        b = np.concatenate(self._bot) if self._bot else np.zeros(0, dtype=np.int16)
        n = max(len(u), len(b))
        u = np.pad(u, (0, n - len(u)))
        b = np.pad(b, (0, n - len(b)))
        return np.stack([u, b], axis=1)  # (n, 2)

    def to_wav_bytes(self) -> bytes:
        stereo = self._stereo()
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(_SR)
            wf.writeframes(stereo.tobytes())
        return buf.getvalue()

    def save_wav(self, path: str):
        with open(path, 'wb') as f:
            f.write(self.to_wav_bytes())

    def reset(self):
        self._user = []
        self._bot = []
