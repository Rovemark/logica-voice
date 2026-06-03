"""
audio_mixer.py — mix background audio under the bot's voice (music bed, hold tone).

Sits on the output side: every AudioOutFrame gets the background track mixed in at a low
gain, looping seamlessly. Useful for hold music, ambient beds, or branded soundscapes on
phone/agent calls. When the bot isn't speaking you can still emit the bed via tick().

Generic: load any mono PCM16 @ sample_rate. No external services.
"""

import os
import io
import wave
import numpy as np

from .processor import FrameProcessor, Direction
from .frames import AudioOutFrame, TTSStartedFrame, TTSStoppedFrame, InterruptionFrame

SAMPLE_RATE_OUT = 24000


class AudioMixer(FrameProcessor):
    """
    Mixes a looping background bed into AudioOutFrame PCM.

    bed_gain   : 0..1 volume of the background under the voice
    duck       : when True, the bed is attenuated further while the bot speaks
    duck_gain  : multiplier applied to bed_gain while speaking (duck=True)
    """

    def __init__(self, bed_path=None, bed_gain=0.15, duck=True, duck_gain=0.5,
                 sample_rate=SAMPLE_RATE_OUT, name=None):
        super().__init__(name)
        self.bed_gain = bed_gain
        self.duck = duck
        self.duck_gain = duck_gain
        self.sample_rate = sample_rate
        self._bed = self._load_bed(bed_path or os.environ.get('LVP_MIXER_BED'))
        self._pos = 0
        self._speaking = False

    def _load_bed(self, path):
        if not path or not os.path.exists(path):
            return None
        try:
            with wave.open(path, 'rb') as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
                pcm = wf.readframes(wf.getnframes())
            arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
            if ch == 2:
                arr = arr.reshape(-1, 2).mean(axis=1)
            if sr != self.sample_rate:
                ratio = self.sample_rate / sr
                idx = np.minimum((np.arange(int(len(arr) * ratio)) / ratio).astype(np.int64),
                                 len(arr) - 1)
                arr = arr[idx]
            return arr
        except Exception:
            return None

    def _bed_chunk(self, n):
        """Return n samples of the looping bed (float32), advancing the play head."""
        if self._bed is None or len(self._bed) == 0:
            return np.zeros(n, dtype=np.float32)
        out = np.empty(n, dtype=np.float32)
        bed, blen, pos = self._bed, len(self._bed), self._pos
        filled = 0
        while filled < n:
            take = min(n - filled, blen - pos)
            out[filled:filled + take] = bed[pos:pos + take]
            filled += take
            pos = (pos + take) % blen
        self._pos = pos
        return out

    def _mix(self, pcm):
        voice = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        bed = self._bed_chunk(len(voice))
        gain = self.bed_gain * (self.duck_gain if (self.duck and self._speaking) else 1.0)
        mixed = voice + bed * gain
        np.clip(mixed, -32768, 32767, out=mixed)
        return mixed.astype(np.int16).tobytes()

    async def process_frame(self, frame, direction):
        if isinstance(frame, TTSStartedFrame):
            self._speaking = True
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TTSStoppedFrame):
            self._speaking = False
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, InterruptionFrame):
            self._speaking = False
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, AudioOutFrame) and frame.pcm and self._bed is not None:
            frame = AudioOutFrame(pcm=self._mix(frame.pcm), text=getattr(frame, 'text', None))
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    async def tick(self, n_samples):
        """Emit a standalone bed chunk (e.g. hold music while idle)."""
        if self._bed is None:
            return
        bed = self._bed_chunk(n_samples) * self.bed_gain
        np.clip(bed, -32768, 32767, out=bed)
        await self.push_frame(AudioOutFrame(pcm=bed.astype(np.int16).tobytes()),
                              Direction.DOWNSTREAM)
