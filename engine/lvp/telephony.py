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


def _pcm8k_to_pcm16k(pcm8_bytes: bytes) -> bytes:
    """linear PCM16 @ 8k → @ 16k (carriers that stream raw PCM, e.g. Exotel)."""
    pcm16, _ = audioop.ratecv(pcm8_bytes, 2, 1, _PHONE_SR, _PIPE_SR, None)
    return pcm16


def _pcm16k_to_pcm8k(pcm16_bytes: bytes, src_sr: int = 24000) -> bytes:
    """linear PCM16 (bot audio) → @ 8k (no companding)."""
    pcm8, _ = audioop.ratecv(pcm16_bytes, 2, 1, src_sr, _PHONE_SR, None)
    return pcm8


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


class _CarrierSerializer:
    """
    Shared base for carrier Media-Streams serializers. Subclasses set the JSON envelope
    keys + codec. `use_ulaw=True` for G.711 μ-law carriers (Twilio/Telnyx/Plivo);
    `use_ulaw=False` for carriers that stream raw linear PCM16 @ 8k (Exotel).
    """
    media_type = 'text'
    use_ulaw = True
    out_event = 'media'
    out_sid_key = 'streamSid'
    start_sid_keys = ('streamSid',)
    extra_media_fields = {}

    def __init__(self, stream_sid=None, bot_sr=24000):
        self.stream_sid = stream_sid
        self.bot_sr = bot_sr

    def _decode_in(self, b64: str) -> bytes:
        raw = base64.b64decode(b64)
        return _ulaw_to_pcm16(raw) if self.use_ulaw else _pcm8k_to_pcm16k(raw)

    def _encode_out(self, pcm16: bytes) -> str:
        out = _pcm16_to_ulaw(pcm16, self.bot_sr) if self.use_ulaw \
            else _pcm16k_to_pcm8k(pcm16, self.bot_sr)
        return base64.b64encode(out).decode('ascii')

    def _read_start_sid(self, msg):
        start = msg.get('start') or {}
        for k in self.start_sid_keys:
            if start.get(k):
                return start[k]
            if msg.get(k):
                return msg[k]
        return None

    def deserialize(self, data):
        if isinstance(data, (bytes, bytearray)):
            data = data.decode('utf-8', errors='ignore')
        try:
            msg = json.loads(data)
        except Exception:
            return {}
        ev = msg.get('event')
        if ev == 'start':
            self.stream_sid = self._read_start_sid(msg)
            return {'type': 'control', 'action': 'start'}
        if ev == 'media':
            payload = (msg.get('media') or {}).get('payload', '')
            return {'type': 'audio', 'pcm': self._decode_in(payload) if payload else b''}
        if ev == 'dtmf':
            digit = (msg.get('dtmf') or {}).get('digit', '') or msg.get('digit', '')
            return {'type': 'dtmf', 'digit': digit}
        if ev in ('stop', 'clear'):
            return {'type': 'control', 'action': 'end'}
        return {}

    def serialize_audio(self, pcm16: bytes) -> str:
        media = {'payload': self._encode_out(pcm16)}
        media.update(self.extra_media_fields)
        envelope = {'event': self.out_event, 'media': media}
        if self.out_sid_key:
            envelope[self.out_sid_key] = self.stream_sid
        return json.dumps(envelope)

    def serialize(self, event: dict) -> str:
        return json.dumps(event)


class TelnyxSerializer(_CarrierSerializer):
    """Telnyx Media Streaming — μ-law PCMU @ 8k; stream identified by `stream_id`."""
    use_ulaw = True
    out_event = 'media'
    out_sid_key = 'stream_id'
    start_sid_keys = ('stream_id',)


class PlivoSerializer(_CarrierSerializer):
    """Plivo Audio Streaming — μ-law @ 8k; outbound uses the `playAudio` event."""
    use_ulaw = True
    out_event = 'playAudio'
    out_sid_key = 'streamId'
    start_sid_keys = ('streamId',)
    extra_media_fields = {'contentType': 'audio/x-mulaw', 'sampleRate': 8000}


class ExotelSerializer(_CarrierSerializer):
    """Exotel Voice Streaming — raw linear PCM16 @ 8k (no companding); `stream_sid`."""
    use_ulaw = False
    out_event = 'media'
    out_sid_key = 'stream_sid'
    start_sid_keys = ('stream_sid',)
