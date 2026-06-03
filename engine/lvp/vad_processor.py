"""
vad_processor.py — Detecção de fala (Silero VAD) + turn detection rápido.

Recebe AudioInFrame (PCM 16k), acumula, e:
  - emite UserStartedSpeakingFrame quando detecta início
  - emite UserStoppedSpeakingFrame (com o WAV) após SILENCE_GAP_MS de silêncio
  - emite InterruptionFrame se o user falar enquanto o bot está respondendo (barge-in)

smart-turn: gap curto (~250ms) pra responsividade, mas com histerese pra não
cortar no meio de pausas naturais.
"""

import io
import time
import wave
import numpy as np

from .processor import FrameProcessor, Direction
from .frames import (
    AudioInFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    InterruptionFrame, ControlFrame,
)

VAD_FRAME_SIZE = 512  # 32ms @ 16kHz (Silero exige 512)
SAMPLE_RATE = 16000


class VADProcessor(FrameProcessor):
    def __init__(self, silence_gap_ms=250, min_utterance_ms=250, threshold=0.5,
                 bot_speaking_getter=None, name=None):
        super().__init__(name)
        from silero_vad import load_silero_vad
        import torch
        self._torch = torch
        # Instância PRÓPRIA do modelo (não compartilha estado RNN entre sessões).
        # load_silero_vad pode cachear globalmente → cada sessão precisa do seu reset.
        self._model = load_silero_vad(onnx=False)
        self._model.reset_states()
        self.threshold = threshold
        self.silence_gap_ms = silence_gap_ms
        self.min_utterance_ms = min_utterance_ms
        # callback que diz se o bot está falando (pra barge-in)
        self._bot_speaking = bot_speaking_getter or (lambda: False)

        self._buf = np.zeros(0, dtype=np.int16)
        self._frames = []
        self._silence_frames = 0
        self._speaking = False
        self._start_ts = 0.0
        self._interrupted_this_turn = False

    def _is_speech(self, frame_int16):
        if len(frame_int16) != VAD_FRAME_SIZE:
            return False
        f = frame_int16.astype(np.float32) / 32768.0
        with self._torch.no_grad():
            prob = self._model(self._torch.from_numpy(f), SAMPLE_RATE).item()
        return prob >= self.threshold

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._reset()
            await self.push_frame(frame, direction)
            return
        if not isinstance(frame, AudioInFrame):
            await super().process_frame(frame, direction)
            return

        new = np.frombuffer(frame.pcm, dtype=np.int16)
        self._buf = np.concatenate([self._buf, new])

        while len(self._buf) >= VAD_FRAME_SIZE:
            chunk = self._buf[:VAD_FRAME_SIZE]
            self._buf = self._buf[VAD_FRAME_SIZE:]
            speech = self._is_speech(chunk)

            # Barge-in: user fala enquanto bot responde → interrompe
            if speech and self._bot_speaking() and not self._interrupted_this_turn:
                self._interrupted_this_turn = True
                await self.push_frame(InterruptionFrame(), Direction.DOWNSTREAM)

            if speech:
                if not self._speaking:
                    self._speaking = True
                    self._start_ts = time.time()
                    self._frames = []
                    await self.push_frame(UserStartedSpeakingFrame(), Direction.DOWNSTREAM)
                self._frames.append(chunk)
                self._silence_frames = 0
            else:
                if self._speaking:
                    self._frames.append(chunk)
                    self._silence_frames += 1

            # Fecha utterance?
            if self._speaking:
                silence_ms = (self._silence_frames * VAD_FRAME_SIZE * 1000) // SAMPLE_RATE
                if silence_ms >= self.silence_gap_ms:
                    await self._close_utterance()

    async def _close_utterance(self):
        total = sum(len(f) for f in self._frames)
        dur_ms = (total * 1000) // SAMPLE_RATE
        frames = self._frames
        self._reset()
        if dur_ms < self.min_utterance_ms:
            return  # ruído curto
        pcm = np.concatenate(frames)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())
        await self.push_frame(
            UserStoppedSpeakingFrame(audio_wav=buf.getvalue(), duration_ms=dur_ms),
            Direction.DOWNSTREAM,
        )

    def _reset(self):
        self._frames = []
        self._silence_frames = 0
        self._speaking = False
        self._interrupted_this_turn = False
        self._buf = np.zeros(0, dtype=np.int16)
