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
from enum import Enum
import numpy as np

from .processor import FrameProcessor, Direction
from .frames import (
    AudioInFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    PartialUtteranceFrame, InterruptionFrame, ControlFrame,
)

VAD_FRAME_SIZE = 512  # 32ms @ 16kHz (Silero exige 512)
SAMPLE_RATE = 16000
FRAME_MS = (VAD_FRAME_SIZE * 1000) // SAMPLE_RATE  # ~32ms


class VADState(Enum):
    """
    4-state machine (Pipecat-style) with hysteresis so a single noisy/quiet frame doesn't
    flip detection:
      QUIET    — silence; waiting for speech onset
      STARTING — heard voice, confirming it lasts >= start_secs before committing
      SPEAKING — confirmed speech; accumulating the utterance
      STOPPING — heard silence mid-speech, confirming it lasts >= silence_gap before closing
    """
    QUIET = 1
    STARTING = 2
    SPEAKING = 3
    STOPPING = 4


def _frames_to_wav(frames):
    pcm = np.concatenate(frames)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


class VADProcessor(FrameProcessor):
    """
    Voice activity detection + turn detection.

    Two turn-detection modes:
      - silence-based (default): close the turn after `silence_gap_ms` of silence.
      - semantic (smart_turn=True): a short silence (`silence_gap_ms`) *triggers* a
        semantic check; the ML model decides if the turn is really complete. If not,
        keep listening until real completion or the `hard_stop_secs` fallback.
    Semantic mode is what makes "I'd like a… [pause] …coffee" not get cut off.
    """

    def __init__(self, silence_gap_ms=250, min_utterance_ms=250, threshold=0.5,
                 bot_speaking_getter=None, smart_turn=False, hard_stop_secs=3.0,
                 partial_interval_ms=0, start_secs=0.0, min_volume=0.0,
                 interruption_strategy=None, allow_interruptions=True, name=None):
        super().__init__(name)
        # Barge-in policy: whether the user can interrupt the bot, and (if so) how decisive
        # their speech must be. None strategy = interrupt on the first voiced frame (legacy).
        self.allow_interruptions = allow_interruptions
        self.interruption_strategy = interruption_strategy
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
        self.hard_stop_ms = hard_stop_secs * 1000
        # Onset confirmation: voice must persist >= start_secs before we commit to SPEAKING
        # (rejects clicks/coughs). 0.0 = commit on the first voice frame (legacy behavior).
        self.start_ms = start_secs * 1000
        # Volume gate: a frame counts as voice only if its RMS (normalized 0..1) >= min_volume,
        # even if the model says speech — rejects steady low-level background noise. 0 = off.
        self.min_volume = min_volume
        # STT streaming: if > 0, emit a partial-audio frame every N ms of speech
        # so the STT can produce interim transcriptions (text appears as you talk).
        self.partial_interval_ms = partial_interval_ms
        self._last_partial_frames = 0
        # callback que diz se o bot está falando (pra barge-in)
        self._bot_speaking = bot_speaking_getter or (lambda: False)

        # Semantic turn detector (lazy — only loaded if enabled)
        self._smart_turn = None
        if smart_turn:
            try:
                from .smart_turn import SmartTurnDetector
                self._smart_turn = SmartTurnDetector()
                print('[vad] smart-turn (semantic) enabled', flush=True)
            except Exception as e:
                print(f'[vad] smart-turn unavailable, falling back to silence-based: {e}', flush=True)

        self._buf = np.zeros(0, dtype=np.int16)
        self._frames = []
        self._silence_frames = 0
        self._state = VADState.QUIET
        self._voice_run_frames = 0   # consecutive voice frames during STARTING
        self._start_ts = 0.0
        self._interrupted_this_turn = False
        self._smart_checked = False  # já rodou o smart-turn nesta pausa?

    @property
    def _speaking(self):
        # SPEAKING or STOPPING both mean "an utterance is in progress".
        return self._state in (VADState.SPEAKING, VADState.STOPPING)

    def _is_speech(self, frame_int16):
        if len(frame_int16) != VAD_FRAME_SIZE:
            return False
        f = frame_int16.astype(np.float32) / 32768.0
        # Volume gate: reject frames quieter than min_volume even if the model fires.
        if self.min_volume > 0.0:
            rms = float(np.sqrt(np.mean(f * f)))
            if rms < self.min_volume:
                return False
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

            # Barge-in: user fala enquanto bot responde → interrompe (se permitido + a
            # estratégia considerar a fala intencional o suficiente).
            if self.allow_interruptions and self._bot_speaking() and not self._interrupted_this_turn:
                strat = self.interruption_strategy
                if speech:
                    fire = True
                    if strat is not None:
                        strat.append_audio(FRAME_MS)
                        fire = strat.should_interrupt()
                    if fire:
                        self._interrupted_this_turn = True
                        if strat is not None:
                            strat.reset()
                        await self.push_frame(InterruptionFrame(), Direction.DOWNSTREAM)
            elif self.interruption_strategy is not None and not self._bot_speaking():
                self.interruption_strategy.reset()   # bot silent → forget accumulated voice

            # ── State machine: QUIET → STARTING → SPEAKING → STOPPING ──
            if self._state == VADState.QUIET:
                if speech:
                    self._state = VADState.STARTING
                    self._voice_run_frames = 1
                    self._frames = [chunk]          # buffer the onset
                    if self.start_ms <= 0:
                        await self._begin_speaking()

            elif self._state == VADState.STARTING:
                if speech:
                    self._voice_run_frames += 1
                    self._frames.append(chunk)
                    if self._voice_run_frames * FRAME_MS >= self.start_ms:
                        await self._begin_speaking()
                else:
                    self._abandon()                 # false start (click/cough) — discard

            elif self._state == VADState.SPEAKING:
                self._frames.append(chunk)
                if speech:
                    self._silence_frames = 0
                    self._smart_checked = False
                    await self._maybe_partial()
                else:
                    self._state = VADState.STOPPING
                    self._silence_frames = 1

            elif self._state == VADState.STOPPING:
                self._frames.append(chunk)
                if speech:
                    self._state = VADState.SPEAKING  # resumed — it was just a pause
                    self._silence_frames = 0
                    self._smart_checked = False
                    await self._maybe_partial()
                else:
                    self._silence_frames += 1

            # Turn detection (only while an utterance is in progress)
            if self._state in (VADState.SPEAKING, VADState.STOPPING):
                silence_ms = (self._silence_frames * VAD_FRAME_SIZE * 1000) // SAMPLE_RATE

                if self._smart_turn is not None:
                    # Semantic: short silence triggers the ML check once; hard-stop is the fallback.
                    if silence_ms >= self.hard_stop_ms:
                        await self._close_utterance()
                    elif silence_ms >= self.silence_gap_ms and not self._smart_checked:
                        self._smart_checked = True
                        if self._semantic_turn_complete():
                            await self._close_utterance()
                        # incomplete → keep listening (waits for more speech or hard-stop)
                else:
                    # Silence-based: close after the gap.
                    if silence_ms >= self.silence_gap_ms:
                        await self._close_utterance()

    async def _begin_speaking(self):
        """Commit STARTING → SPEAKING and announce the user turn."""
        self._state = VADState.SPEAKING
        self._start_ts = time.time()
        self._silence_frames = 0
        self._last_partial_frames = 0
        self._smart_checked = False
        await self.push_frame(UserStartedSpeakingFrame(), Direction.DOWNSTREAM)

    async def _maybe_partial(self):
        """STT streaming: emit a partial every partial_interval_ms of speech."""
        if self.partial_interval_ms <= 0:
            return
        nframes = len(self._frames)
        elapsed = (nframes * VAD_FRAME_SIZE * 1000) // SAMPLE_RATE
        last_elapsed = (self._last_partial_frames * VAD_FRAME_SIZE * 1000) // SAMPLE_RATE
        if elapsed - last_elapsed >= self.partial_interval_ms:
            self._last_partial_frames = nframes
            await self.push_frame(
                PartialUtteranceFrame(audio_wav=_frames_to_wav(self._frames), duration_ms=elapsed),
                Direction.DOWNSTREAM,
            )

    def _abandon(self):
        """Drop an unconfirmed onset (STARTING that didn't last start_secs)."""
        self._frames = []
        self._silence_frames = 0
        self._voice_run_frames = 0
        self._smart_checked = False
        self._state = VADState.QUIET

    def _semantic_turn_complete(self) -> bool:
        """Run the smart-turn model on the accumulated audio (last 8 s)."""
        try:
            pcm = np.concatenate(self._frames).astype(np.float32) / 32768.0
            complete, prob = self._smart_turn.is_turn_complete(pcm)
            return complete
        except Exception as e:
            print(f'[vad] smart-turn inference failed, closing turn: {e}', flush=True)
            return True  # fail-safe: close rather than hang

    async def _close_utterance(self):
        total = sum(len(f) for f in self._frames)
        dur_ms = (total * 1000) // SAMPLE_RATE
        frames = self._frames
        self._reset()
        if dur_ms < self.min_utterance_ms:
            return  # ruído curto
        await self.push_frame(
            UserStoppedSpeakingFrame(audio_wav=_frames_to_wav(frames), duration_ms=dur_ms),
            Direction.DOWNSTREAM,
        )

    def _reset(self):
        self._frames = []
        self._silence_frames = 0
        self._voice_run_frames = 0
        self._state = VADState.QUIET
        self._interrupted_this_turn = False
        self._smart_checked = False
        self._buf = np.zeros(0, dtype=np.int16)
