"""
streaming_stt.py — real-time streaming STT over WebSocket (Deepgram/AssemblyAI-style).

Unlike the batch STTProcessor (transcribe once at end-of-turn), this keeps a WS open to
a streaming STT service and feeds audio continuously, emitting interim transcriptions as
the user speaks and a final one when the service flags is_final. Lower latency + earlier
barge-in than batch Whisper.

Generic: configure the WS URL + auth header via env. Defaults match Deepgram's protocol
(send raw PCM16; receive {"is_final":bool, "channel":{"alternatives":[{"transcript":...}]}}).

  LVP_STREAM_STT_URL   wss endpoint
  LVP_STREAM_STT_AUTH  Authorization header value (e.g. "Token <key>")
"""

import os
import json
import asyncio

from .processor import FrameProcessor, Direction
from .frames import (
    AudioInFrame, TranscriptionFrame, InterimTranscriptionFrame,
    UserStoppedSpeakingFrame, InterruptionFrame,
)

STREAM_STT_URL = os.environ.get('LVP_STREAM_STT_URL', '')
STREAM_STT_AUTH = os.environ.get('LVP_STREAM_STT_AUTH', '')


class StreamingSTTProcessor(FrameProcessor):
    def __init__(self, url=STREAM_STT_URL, auth=STREAM_STT_AUTH,
                 sample_rate=16000, name=None):
        super().__init__(name)
        self.url = url
        self.auth = auth
        self.sample_rate = sample_rate
        self._ws = None
        self._reader = None

    async def _ensure_ws(self):
        if self._ws is not None:
            return
        import websockets
        headers = {'Authorization': self.auth} if self.auth else {}
        url = self.url
        if '?' not in url:
            url += f'?encoding=linear16&sample_rate={self.sample_rate}&interim_results=true'
        self._ws = await websockets.connect(url, additional_headers=headers)
        self._reader = self._spawn(self._read_loop())

    async def _read_loop(self):
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                except Exception:
                    continue
                text, is_final = self._parse(data)
                if not text:
                    continue
                if is_final:
                    await self.push_frame(TranscriptionFrame(text=text), Direction.DOWNSTREAM)
                else:
                    await self.push_frame(InterimTranscriptionFrame(text=text), Direction.DOWNSTREAM)
        except Exception:
            pass

    @staticmethod
    def _parse(data):
        # Deepgram shape
        try:
            alt = data['channel']['alternatives'][0]
            return alt.get('transcript', '').strip(), bool(data.get('is_final'))
        except (KeyError, IndexError, TypeError):
            pass
        # Generic {text, final}
        return (data.get('text', '') or '').strip(), bool(data.get('final'))

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._cancel_tasks()
            await self._close_ws()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, AudioInFrame) and frame.pcm and self.url:
            try:
                await self._ensure_ws()
                await self._ws.send(frame.pcm)
            except Exception:
                pass
            # also forward audio (VAD downstream still wants it)
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, UserStoppedSpeakingFrame):
            # tell the service to finalize, but DON'T re-transcribe (we stream)
            try:
                if self._ws:
                    await self._ws.send(json.dumps({'type': 'Finalize'}))
            except Exception:
                pass
            # swallow the WAV — final text comes from the stream, not batch
            return
        await super().process_frame(frame, direction)

    async def _close_ws(self):
        try:
            if self._ws:
                await self._ws.close()
        except Exception:
            pass
        self._ws = None

    async def on_end(self):
        await self._close_ws()
