"""
telephony.py — phone integration (Twilio/Telnyx Media Streams + DTMF).

Phone carriers stream call audio as base64 μ-law (G.711) at 8 kHz over a WebSocket,
with provider-specific JSON envelopes. TwilioSerializer converts between that wire
format and our PCM frames (μ-law 8k ↔ PCM 16k), and surfaces DTMF key presses.

Use it as the serializer for a WebSocketTransport when the client is a phone call:
    transport = WebSocketTransport(ws, serializer=TwilioSerializer())
"""

import audioop  # stdlib (Python <3.13) ; for 3.13+ use audioop-lts shim
import base64
import json

import numpy as np

_PHONE_SR = 8000
_PIPE_SR = 16000


def _ulaw_to_pcm16(ulaw_bytes: bytes) -> bytes:
    """μ-law 8k → linear PCM16 16k (for the pipeline)."""
    pcm8 = audioop.ulaw2lin(ulaw_bytes, 2)               # μ-law → 16-bit PCM @ 8k
    pcm16, _ = audioop.ratecv(pcm8, 2, 1, _PHONE_SR, _PIPE_SR, None)
    return pcm16


def _pcm16_to_ulaw(pcm16_bytes: bytes, src_sr: int = 24000) -> bytes:
    """linear PCM16 (bot audio) → μ-law 8k (for the carrier)."""
    pcm8, _ = audioop.ratecv(pcm16_bytes, 2, 1, src_sr, _PHONE_SR, None)
    return audioop.lin2ulaw(pcm8, 2)


class TwilioSerializer:
    """
    Twilio Media Streams framing:
      inbound  : {"event":"media","media":{"payload": base64-μ-law}}  | {"event":"dtmf",...}
      outbound : {"event":"media","streamSid":..., "media":{"payload": base64-μ-law}}
    """
    media_type = 'text'

    def __init__(self, stream_sid=None, bot_sr=24000):
        self.stream_sid = stream_sid
        self.bot_sr = bot_sr

    def deserialize(self, data):
        """Carrier message → normalized event dict the runner understands."""
        if isinstance(data, (bytes, bytearray)):
            data = data.decode('utf-8', errors='ignore')
        try:
            msg = json.loads(data)
        except Exception:
            return {}
        ev = msg.get('event')
        if ev == 'start':
            self.stream_sid = msg.get('streamSid') or (msg.get('start') or {}).get('streamSid')
            return {'type': 'control', 'action': 'start'}
        if ev == 'media':
            payload = (msg.get('media') or {}).get('payload', '')
            pcm = _ulaw_to_pcm16(base64.b64decode(payload)) if payload else b''
            return {'type': 'audio', 'pcm': pcm}
        if ev == 'dtmf':
            digit = (msg.get('dtmf') or {}).get('digit', '')
            return {'type': 'dtmf', 'digit': digit}
        if ev == 'stop':
            return {'type': 'control', 'action': 'end'}
        return {}

    def serialize_audio(self, pcm16: bytes) -> str:
        """Bot PCM → Twilio outbound media message."""
        ulaw = _pcm16_to_ulaw(pcm16, self.bot_sr)
        return json.dumps({
            'event': 'media',
            'streamSid': self.stream_sid,
            'media': {'payload': base64.b64encode(ulaw).decode('ascii')},
        })

    # FrameSerializer-compatible passthrough for non-audio events
    def serialize(self, event: dict) -> str:
        return json.dumps(event)
