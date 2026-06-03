"""
streaming_tts.py — token-streaming TTS over WebSocket (Cartesia/ElevenLabs-WS-style).

The batch TTSProcessor waits for a full sentence, POSTs it, waits for the whole WAV.
This one keeps a WS open and streams text in as the LLM generates it (word by word),
receiving audio chunks back incrementally — first audio out before the sentence even
finishes. Lowest possible TTFB when the backend supports it.

Generic: point LVP_STREAM_TTS_URL at any WS that accepts {"text": "..."} / {"flush": true}
messages and returns binary PCM (or base64 in {"audio": "..."}). Falls back gracefully.

  LVP_STREAM_TTS_URL   wss endpoint
  LVP_STREAM_TTS_AUTH  Authorization header value
  LVP_STREAM_TTS_VOICE voice id passed on the open message
"""

import os
import json
import base64
import asyncio

from .processor import FrameProcessor, Direction
from .frames import (
    LLMTokenFrame, LLMFullResponseFrame, TextSentenceFrame, AudioOutFrame,
    TTSStartedFrame, TTSStoppedFrame, InterruptionFrame, ErrorFrame,
)

STREAM_TTS_URL = os.environ.get('LVP_STREAM_TTS_URL', '')
STREAM_TTS_AUTH = os.environ.get('LVP_STREAM_TTS_AUTH', '')
STREAM_TTS_VOICE = os.environ.get('LVP_STREAM_TTS_VOICE', '')
SAMPLE_RATE_OUT = 24000


class StreamingTTSProcessor(FrameProcessor):
    """
    Feeds text tokens into a streaming TTS WS and pushes AudioOutFrame chunks as they
    arrive. Accepts either LLMTokenFrame (raw stream) or TextSentenceFrame (aggregated).
    On LLMFullResponseFrame it flushes; on InterruptionFrame it closes the WS (barge-in).
    """

    def __init__(self, url=STREAM_TTS_URL, auth=STREAM_TTS_AUTH, voice=STREAM_TTS_VOICE,
                 sample_rate=SAMPLE_RATE_OUT, name=None):
        super().__init__(name)
        self.url = url
        self.auth = auth
        self.voice = voice
        self.sample_rate = sample_rate
        self._ws = None
        self._reader = None
        self._speaking = False

    async def _ensure_ws(self):
        if self._ws is not None:
            return
        import websockets
        headers = {'Authorization': self.auth} if self.auth else {}
        self._ws = await websockets.connect(self.url, additional_headers=headers)
        # open message: voice + output format
        try:
            await self._ws.send(json.dumps({
                'type': 'start', 'voice': self.voice,
                'sample_rate': self.sample_rate, 'encoding': 'pcm_s16le',
            }))
        except Exception:
            pass
        self._reader = self._spawn(self._read_loop())

    async def _read_loop(self):
        try:
            async for message in self._ws:
                pcm = None
                if isinstance(message, (bytes, bytearray)):
                    pcm = bytes(message)
                else:
                    try:
                        data = json.loads(message)
                    except Exception:
                        continue
                    if data.get('audio'):
                        pcm = base64.b64decode(data['audio'])
                    elif data.get('done'):
                        if self._speaking:
                            self._speaking = False
                            await self.push_frame(TTSStoppedFrame(), Direction.DOWNSTREAM)
                        continue
                if not pcm:
                    continue
                if not self._speaking:
                    self._speaking = True
                    await self.push_frame(TTSStartedFrame(), Direction.DOWNSTREAM)
                await self.push_frame(AudioOutFrame(pcm=pcm), Direction.DOWNSTREAM)
        except Exception:
            pass

    async def _send_text(self, text):
        if not text:
            return
        try:
            await self._ensure_ws()
            await self._ws.send(json.dumps({'type': 'text', 'text': text}))
        except Exception as e:
            await self.push_frame(ErrorFrame(message=f'StreamTTS: {e}', source=self.name),
                                  Direction.DOWNSTREAM)

    async def _flush(self):
        try:
            if self._ws:
                await self._ws.send(json.dumps({'type': 'flush'}))
        except Exception:
            pass

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._cancel_tasks()
            await self._close_ws()
            await self.push_frame(frame, direction)
            return
        if not self.url:
            # no streaming backend configured — passthrough (let batch TTS handle it)
            await super().process_frame(frame, direction)
            return
        if isinstance(frame, LLMTokenFrame):
            await self._send_text(frame.text)
            return
        if isinstance(frame, TextSentenceFrame):
            await self._send_text(frame.text + ' ')
            return
        if isinstance(frame, LLMFullResponseFrame):
            await self._flush()
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    async def _close_ws(self):
        self._speaking = False
        try:
            if self._ws:
                await self._ws.close()
        except Exception:
            pass
        self._ws = None

    async def on_end(self):
        await self._close_ws()
