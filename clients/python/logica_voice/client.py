"""
client.py — LogicaVoiceClient (Python): talk to a live Logica Voice pipeline.

Async client over one WebSocket — mirrors @logica-voice/client (JS). Feed it mic PCM
(16 kHz int16 mono), get transcripts, streaming tokens, and the bot's voice (24 kHz int16)
back, with one-call barge-in.

    vc = LogicaVoiceClient("ws://127.0.0.1:8915")

    @vc.on("stt_final")
    def _(e): print("you said:", e["text"])

    @vc.on("audio")
    def _(pcm): speaker.write(pcm)        # bot voice, PCM 24 kHz int16

    await vc.connect()
    await vc.send_audio(mic_pcm_16k)
    await vc.interrupt()                   # talk over the bot
    await vc.run()                         # process events until the socket closes
"""

import json
import asyncio

SAMPLE_RATE_IN = 16000     # mic → server
SAMPLE_RATE_OUT = 24000    # server → speaker

# JSON event types the server emits (binary messages are raw bot-voice PCM).
SERVER_EVENTS = (
    'ready', 'stt_partial', 'stt_final', 'llm_token', 'llm_done',
    'tts_chunk', 'vad', 'interrupted', 'metrics', 'error',
)


def parse_event(data):
    """Text frame → event dict (or None if not valid JSON with a `type`)."""
    try:
        obj = json.loads(data)
    except Exception:
        return None
    return obj if isinstance(obj, dict) and 'type' in obj else None


class LogicaVoiceClient:
    """
    Register handlers with @vc.on(event); they receive the event dict, except "audio"
    which receives raw PCM bytes (the bot's voice). Handlers may be sync or async.
    """

    def __init__(self, url):
        self.url = url
        self._ws = None
        self._handlers = {}
        self._reader = None

    # ── typed-ish event registration ───────────────────────────────────
    def on(self, event):
        """Decorator: @vc.on('stt_final'). Events: the SERVER_EVENTS + 'audio'/'close'."""
        def deco(fn):
            self._handlers.setdefault(event, []).append(fn)
            return fn
        return deco

    def _emit(self, event, *args):
        for cb in self._handlers.get(event, []):
            try:
                res = cb(*args)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

    # ── lifecycle ──────────────────────────────────────────────────────
    async def connect(self):
        """Open the socket and wait for the server's `ready` event."""
        import websockets
        self._ws = await websockets.connect(self.url, max_size=20_000_000)
        ready = None
        async for msg in self._ws:
            if isinstance(msg, (bytes, bytearray)):
                self._emit('audio', bytes(msg))
                continue
            evt = parse_event(msg)
            if not evt:
                continue
            self._emit(evt['type'], evt)
            if evt['type'] == 'ready':
                ready = evt
                break
        return ready

    async def run(self):
        """Process incoming messages until the socket closes."""
        try:
            async for msg in self._ws:
                if isinstance(msg, (bytes, bytearray)):
                    self._emit('audio', bytes(msg))
                else:
                    evt = parse_event(msg)
                    if evt:
                        self._emit(evt['type'], evt)
        finally:
            self._emit('close')

    async def send_audio(self, pcm):
        """Send mic audio — PCM 16 kHz int16 mono (bytes)."""
        await self._ws.send(bytes(pcm))

    async def interrupt(self):
        """Barge-in: stop the bot speaking now."""
        await self._ws.send(json.dumps({'type': 'control', 'action': 'interrupt'}))

    async def end(self):
        await self._ws.send(json.dumps({'type': 'control', 'action': 'end'}))

    async def close(self):
        try:
            if self._ws:
                await self._ws.close()
        finally:
            self._ws = None
