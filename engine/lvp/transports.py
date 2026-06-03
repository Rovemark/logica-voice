"""
transports.py — transport abstraction (WebSocket + WebRTC).

A transport carries audio + control between the client and the pipeline. The pipeline
doesn't care which one — it just gets AudioInFrame and emits AudioOutFrame/events.

  - BaseTransport      : the interface
  - WebSocketTransport : binary PCM + JSON control over a WS (the default, in runner.py)
  - WebRTCTransport    : low-jitter audio over WebRTC (aiortc) for browsers/mobile

WebRTC gives real-time audio with far less jitter than WS — preferred for browser
clients. It needs `aiortc` and an SDP signaling exchange (offer/answer) which the app
provides; this class handles the peer connection + audio tracks once signaled.
"""

import asyncio


class BaseTransport:
    """Interface: feed audio into the pipeline, send audio/events back to the client."""

    def __init__(self):
        self.on_audio = None     # async callback(pcm_bytes)
        self.on_event = None     # async callback(dict)
        self.on_connect = None
        self.on_disconnect = None

    async def send_audio(self, pcm: bytes):
        raise NotImplementedError

    async def send_event(self, event: dict):
        raise NotImplementedError

    async def close(self):
        pass


class WebSocketTransport(BaseTransport):
    """Binary PCM + JSON control over a websocket (matches runner.py's native protocol)."""

    def __init__(self, ws, serializer=None):
        super().__init__()
        self.ws = ws
        if serializer is None:
            from .serializers import JSONFrameSerializer
            serializer = JSONFrameSerializer()
        self.serializer = serializer

    async def send_audio(self, pcm: bytes):
        await self.ws.send(pcm)

    async def send_event(self, event: dict):
        await self.ws.send(self.serializer.serialize(event))

    async def run(self):
        if self.on_connect:
            await self.on_connect()
        try:
            async for message in self.ws:
                if isinstance(message, bytes):
                    if self.on_audio:
                        await self.on_audio(message)
                else:
                    if self.on_event:
                        try:
                            await self.on_event(self.serializer.deserialize(message))
                        except Exception:
                            pass
        finally:
            if self.on_disconnect:
                await self.on_disconnect()


class WebRTCTransport(BaseTransport):
    """
    WebRTC audio transport via aiortc. The app does SDP signaling and hands us the
    offer; we answer and wire the audio tracks. Mic audio (PCM 16k) flows to on_audio;
    bot audio (PCM 24k) is pushed via send_audio onto an outgoing track.

    Requires `aiortc` (+ `av`). Install: pip install aiortc av
    """

    def __init__(self, sample_rate_in=16000, sample_rate_out=24000):
        super().__init__()
        self.sample_rate_in = sample_rate_in
        self.sample_rate_out = sample_rate_out
        self.pc = None
        self._out_queue = asyncio.Queue()

    async def handle_offer(self, sdp: str, sdp_type: str = 'offer') -> dict:
        """Accept an SDP offer, return the answer {sdp, type} for the client."""
        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
            import av  # noqa
            import numpy as np
        except ImportError:
            raise RuntimeError("WebRTC requires: pip install aiortc av")

        self.pc = RTCPeerConnection()
        transport = self

        @self.pc.on('track')
        async def on_track(track):
            if track.kind == 'audio':
                asyncio.create_task(transport._consume_audio(track))

        # Outgoing audio track that pulls from our queue
        class _BotTrack(MediaStreamTrack):
            kind = 'audio'

            async def recv(self):
                import av
                import numpy as np
                pcm = await transport._out_queue.get()
                samples = np.frombuffer(pcm, dtype=np.int16)
                frame = av.AudioFrame.from_ndarray(
                    samples.reshape(1, -1), format='s16', layout='mono')
                frame.sample_rate = transport.sample_rate_out
                return frame

        self.pc.addTrack(_BotTrack())

        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=sdp_type))
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        if self.on_connect:
            await self.on_connect()
        return {'sdp': self.pc.localDescription.sdp, 'type': self.pc.localDescription.type}

    async def _consume_audio(self, track):
        import numpy as np
        try:
            while True:
                frame = await track.recv()
                pcm = frame.to_ndarray().astype(np.int16).tobytes()
                if self.on_audio:
                    await self.on_audio(pcm)
        except Exception:
            if self.on_disconnect:
                await self.on_disconnect()

    async def send_audio(self, pcm: bytes):
        await self._out_queue.put(pcm)

    async def send_event(self, event: dict):
        # WebRTC data channel could carry events; for now events go via the signaling app.
        pass

    async def close(self):
        if self.pc:
            await self.pc.close()
