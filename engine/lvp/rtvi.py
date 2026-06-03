"""
rtvi.py — RTVI-style event protocol over the WebSocket.

RTVI is the de-facto client/server message standard for voice agents. Emitting these
events lets standard RTVI client SDKs (web/React/iOS/Android) talk to the engine with
no custom glue. RTVIObserver watches the pipeline and translates frames into RTVI
messages; it's opt-in (LVP_RTVI=true) and runs alongside the native protocol.

Message shape: {"type": "<rtvi-event>", "data": {...}}
Key events:
  bot-ready, user-started-speaking, user-stopped-speaking,
  user-transcription (final/interim), bot-llm-text, bot-llm-stopped,
  bot-tts-text, bot-tts-started, bot-tts-stopped, metrics
"""

import json

from .processor import BaseObserver, Direction
from .frames import (
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame, TranscriptionFrame,
    InterimTranscriptionFrame, LLMTokenFrame, LLMFullResponseFrame,
    TextSentenceFrame, AudioOutFrame, MetricsFrame, InterruptionFrame, ErrorFrame,
)


class RTVIObserver(BaseObserver):
    def __init__(self, ws):
        self.ws = ws
        self._bot_speaking = False

    async def _send(self, etype, data=None):
        try:
            await self.ws.send(json.dumps({'type': etype, 'data': data or {}}))
        except Exception:
            pass

    async def bot_ready(self):
        await self._send('bot-ready', {'version': '1.0', 'engine': 'lvp'})

    async def on_push_frame(self, processor, frame, direction):
        if direction != Direction.DOWNSTREAM:
            return
        if isinstance(frame, UserStartedSpeakingFrame):
            await self._send('user-started-speaking')
        elif isinstance(frame, UserStoppedSpeakingFrame):
            await self._send('user-stopped-speaking')
        elif isinstance(frame, TranscriptionFrame):
            await self._send('user-transcription', {'text': frame.text, 'final': True})
        elif isinstance(frame, InterimTranscriptionFrame):
            await self._send('user-transcription', {'text': frame.text, 'final': False})
        elif isinstance(frame, LLMTokenFrame):
            await self._send('bot-llm-text', {'text': frame.text})
        elif isinstance(frame, LLMFullResponseFrame):
            await self._send('bot-llm-stopped', {'text': frame.text})
        elif isinstance(frame, TextSentenceFrame):
            await self._send('bot-tts-text', {'text': frame.text})
        elif isinstance(frame, AudioOutFrame):
            if not self._bot_speaking:
                self._bot_speaking = True
                await self._send('bot-tts-started')
            # audio bytes go on the binary channel (native); RTVI clients read PCM there
        elif isinstance(frame, InterruptionFrame):
            self._bot_speaking = False
            await self._send('user-interruption')
        elif isinstance(frame, MetricsFrame):
            self._bot_speaking = False
            await self._send('metrics', frame.metrics)
        elif isinstance(frame, ErrorFrame):
            await self._send('error', {'message': frame.message})
