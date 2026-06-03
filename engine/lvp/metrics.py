"""
metrics.py — Latency observability for the LVP pipeline.

A framework that lives or dies on latency must measure it. MetricsCollector is a
BaseObserver that watches frames flow by and computes, per turn:

  - stt_ms      : end-of-speech → final transcription
  - llm_ttft_ms : transcription → first LLM token
  - tts_ttfb_ms : first sentence → first audio chunk
  - total_ms    : end-of-speech → first audio out  (the number users feel)

Emits a MetricsFrame at end of turn and (optionally) logs a one-line summary.
Zero overhead when disabled.
"""

import time

from .processor import BaseObserver, Direction
from .frames import (
    UserStoppedSpeakingFrame, TranscriptionFrame, LLMTokenFrame,
    LLMFullResponseFrame, TextSentenceFrame, AudioOutFrame, MetricsFrame,
)


class MetricsCollector(BaseObserver):
    def __init__(self, log=True, on_metrics=None):
        self.log = log
        self.on_metrics = on_metrics
        self._reset()

    def _reset(self):
        self.t_user_stopped = None
        self.t_stt = None
        self.t_llm_first = None
        self.t_sentence_first = None
        self.t_audio_first = None
        self._counted_audio = False

    async def on_push_frame(self, processor, frame, direction):
        if direction != Direction.DOWNSTREAM:
            return
        now = time.time()

        if isinstance(frame, UserStoppedSpeakingFrame):
            # new turn starts measuring
            self._reset()
            self.t_user_stopped = now
        elif isinstance(frame, TranscriptionFrame) and self.t_stt is None:
            self.t_stt = now
        elif isinstance(frame, LLMTokenFrame) and self.t_llm_first is None:
            self.t_llm_first = now
        elif isinstance(frame, TextSentenceFrame) and self.t_sentence_first is None:
            self.t_sentence_first = now
        elif isinstance(frame, AudioOutFrame) and self.t_audio_first is None:
            self.t_audio_first = now
            await self._emit(processor)

    async def _emit(self, processor):
        if self.t_user_stopped is None:
            return
        base = self.t_user_stopped

        def ms(a, b):
            return round((b - a) * 1000) if a and b else None

        m = {
            'stt_ms': ms(base, self.t_stt),
            'llm_ttft_ms': ms(self.t_stt, self.t_llm_first),
            'tts_ttfb_ms': ms(self.t_sentence_first, self.t_audio_first),
            'total_ms': ms(base, self.t_audio_first),
        }
        if self.log:
            print(f"[metrics] STT={m['stt_ms']}ms · LLM_TTFT={m['llm_ttft_ms']}ms · "
                  f"TTS_TTFB={m['tts_ttfb_ms']}ms · TOTAL={m['total_ms']}ms", flush=True)
        if self.on_metrics:
            try:
                self.on_metrics(m)
            except Exception:
                pass
        # Emit a MetricsFrame downstream so the transport can relay it to the client.
        try:
            await processor.push_frame(MetricsFrame(metrics=m), Direction.DOWNSTREAM)
        except Exception:
            pass
