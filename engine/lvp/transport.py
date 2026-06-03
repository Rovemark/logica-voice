"""
transport.py — entrada/saída do pipeline via WebSocket.

TransportOutput: recebe AudioOutFrame (+ eventos) e manda pro cliente WS.
  - AudioOutFrame → binário PCM 24k
  - TranscriptionFrame/LLM/etc → JSON de telemetria (UI mostra texto)

A ENTRADA não é um processor — o servidor injeta AudioInFrame direto no pipeline
conforme recebe binário do cliente (ver runner.py).

Genérico: só conhece o protocolo WS do Logica Voice, nada externo.
"""

import json
from .processor import FrameProcessor, Direction
from .frames import (
    AudioOutFrame, TranscriptionFrame, InterimTranscriptionFrame,
    LLMTokenFrame, LLMFullResponseFrame, UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame, InterruptionFrame, ErrorFrame, EndFrame,
    MetricsFrame,
)


class TransportOutput(FrameProcessor):
    """Último processor: serializa frames pro cliente WS."""

    def __init__(self, ws, on_bot_audio=None, name=None):
        super().__init__(name)
        self.ws = ws
        # callback opcional pra marcar "bot está falando" (echo guard / barge-in)
        self._on_bot_audio = on_bot_audio

    async def process_frame(self, frame, direction):
        try:
            if isinstance(frame, AudioOutFrame):
                await self.ws.send(json.dumps({'type': 'tts_chunk', 'size': len(frame.pcm), 'text': frame.text}))
                await self.ws.send(frame.pcm)
                if self._on_bot_audio:
                    self._on_bot_audio(len(frame.pcm))
                return
            if isinstance(frame, TranscriptionFrame):
                await self.ws.send(json.dumps({'type': 'stt_final', 'text': frame.text}))
                return
            if isinstance(frame, InterimTranscriptionFrame):
                await self.ws.send(json.dumps({'type': 'stt_partial', 'text': frame.text}))
                return
            if isinstance(frame, LLMTokenFrame):
                await self.ws.send(json.dumps({'type': 'llm_token', 'text': frame.text}))
                return
            if isinstance(frame, LLMFullResponseFrame):
                await self.ws.send(json.dumps({'type': 'llm_done', 'text': frame.text}))
                return
            if isinstance(frame, UserStartedSpeakingFrame):
                await self.ws.send(json.dumps({'type': 'vad', 'speaking': True}))
                return
            if isinstance(frame, UserStoppedSpeakingFrame):
                await self.ws.send(json.dumps({'type': 'vad', 'speaking': False}))
                return
            if isinstance(frame, InterruptionFrame):
                await self.ws.send(json.dumps({'type': 'interrupted'}))
                return
            if isinstance(frame, ErrorFrame):
                await self.ws.send(json.dumps({'type': 'error', 'message': frame.message}))
                return
            if isinstance(frame, MetricsFrame):
                await self.ws.send(json.dumps({'type': 'metrics', 'metrics': frame.metrics}))
                return
        except Exception:
            pass  # WS pode ter fechado — ignora
