"""Group E: interruption strategies, watchdog, GatedProcessor, serializers, telephony."""

from conftest import run, pipeline, feed, of_type
from lvp.processor import Direction
from lvp.interruptions import (
    AlwaysInterruptStrategy, MinSpeechDurationStrategy, MinWordsInterruptionStrategy,
)
from lvp.filters import GatedProcessor
from lvp.watchdog import WatchdogObserver
from lvp.frames import (
    AudioOutFrame, OutputImageFrame, InterruptionFrame, HeartbeatFrame,
)
from lvp.serializers import (
    JSONFrameSerializer, MsgpackFrameSerializer, ProtobufFrameSerializer, get_serializer,
)


class _P:
    def __init__(self, name):
        self.name = name


# ─── D3 Interruption strategies (pure) ───────────────────────────────

def test_always_strategy():
    s = AlwaysInterruptStrategy()
    assert s.should_interrupt() is True


def test_min_speech_duration_strategy():
    s = MinSpeechDurationStrategy(min_ms=300)
    s.append_audio(100); s.append_audio(100)
    assert s.should_interrupt() is False     # 200 < 300
    s.append_audio(150)
    assert s.should_interrupt() is True       # 350 >= 300
    s.reset()
    assert s.should_interrupt() is False


def test_min_words_strategy():
    s = MinWordsInterruptionStrategy(min_words=2)
    s.append_text('para')
    assert s.should_interrupt() is False
    s.append_text('para tudo')
    assert s.should_interrupt() is True


# ─── E1 Watchdog ─────────────────────────────────────────────────────

def test_watchdog_completes_on_tail():
    wd = WatchdogObserver(tail_name='Tail', timeout_secs=0)
    run(wd.on_push_frame(_P('Head'), HeartbeatFrame(seq=1), Direction.DOWNSTREAM))
    run(wd.on_push_frame(_P('Tail'), HeartbeatFrame(seq=1), Direction.DOWNSTREAM))
    assert wd.check() == []     # reached the tail → completed, nothing stalled


def test_watchdog_detects_stall_and_names_stage():
    stalls = []
    wd = WatchdogObserver(tail_name='Tail', timeout_secs=0,
                          on_stall=lambda seq, stage: stalls.append((seq, stage)))
    run(wd.on_push_frame(_P('Head'), HeartbeatFrame(seq=7), Direction.DOWNSTREAM))
    run(wd.on_push_frame(_P('STT'), HeartbeatFrame(seq=7), Direction.DOWNSTREAM))
    # never reached Tail; timeout 0 → flagged immediately, pointing at the last stage
    assert wd.check() == [(7, 'STT')]
    assert stalls == [(7, 'STT')]
    assert wd.check() == []      # idempotent — not reported twice


# ─── E2 GatedProcessor ───────────────────────────────────────────────

def test_gate_holds_then_releases_in_order():
    # hold AudioOutFrame until an OutputImageFrame arrives, then flush in order
    head, sink = pipeline(GatedProcessor(
        start_open=False,
        open_when=lambda f: isinstance(f, OutputImageFrame),
        gated_types=(AudioOutFrame,)))
    run(feed(head, [
        AudioOutFrame(pcm=b'1'),
        AudioOutFrame(pcm=b'2'),
        OutputImageFrame(image=b'img'),   # opens the gate
        AudioOutFrame(pcm=b'3'),
    ]))
    pcms = [f.pcm for f in of_type(sink.out, AudioOutFrame)]
    assert pcms == [b'1', b'2', b'3']     # held ones flushed first, then live
    assert of_type(sink.out, OutputImageFrame)


def test_gate_open_passes_through():
    head, sink = pipeline(GatedProcessor(start_open=True, gated_types=(AudioOutFrame,)))
    run(feed(head, [AudioOutFrame(pcm=b'a')]))
    assert [f.pcm for f in of_type(sink.out, AudioOutFrame)] == [b'a']


def test_gate_interruption_drops_held():
    head, sink = pipeline(GatedProcessor(
        start_open=False, open_when=lambda f: False, gated_types=(AudioOutFrame,)))
    run(feed(head, [AudioOutFrame(pcm=b'x'), InterruptionFrame()]))
    assert of_type(sink.out, AudioOutFrame) == []   # held frame dropped on interruption


# ─── E3 Serializers ──────────────────────────────────────────────────

def test_json_roundtrip():
    s = JSONFrameSerializer()
    ev = {'type': 'control', 'action': 'start'}
    assert s.deserialize(s.serialize(ev)) == ev


def test_msgpack_roundtrip():
    s = MsgpackFrameSerializer()
    ev = {'type': 'audio', 'pcm': b'\x01\x02\x03', 'sample_rate': 24000}
    out = s.deserialize(s.serialize(ev))
    assert out['pcm'] == b'\x01\x02\x03' and out['sample_rate'] == 24000


def test_protobuf_roundtrip_audio():
    s = ProtobufFrameSerializer()
    ev = {'type': 'audio', 'pcm': b'\x10\x20\x30', 'sample_rate': 24000}
    blob = s.serialize(ev)
    assert isinstance(blob, bytes)
    out = s.deserialize(blob)
    assert out['type'] == 'audio'
    assert out['pcm'] == b'\x10\x20\x30'
    assert out['sample_rate'] == 24000


def test_protobuf_roundtrip_extra_fields():
    s = ProtobufFrameSerializer()
    ev = {'type': 'dtmf', 'digit': '5', 'foo': 'bar'}
    out = s.deserialize(s.serialize(ev))
    assert out['type'] == 'dtmf' and out['digit'] == '5' and out['foo'] == 'bar'


def test_protobuf_smaller_than_json_for_audio():
    import base64
    audio = b'\x00' * 4000
    pb = len(ProtobufFrameSerializer().serialize({'type': 'audio', 'pcm': audio}))
    # JSON can't hold raw bytes — the realistic way it carries audio is base64.
    js = len(JSONFrameSerializer().serialize(
        {'type': 'audio', 'pcm': base64.b64encode(audio).decode()}).encode())
    assert pb < js   # protobuf sends raw bytes; JSON must base64 (+33%)


def test_get_serializer_dispatch():
    assert isinstance(get_serializer('json'), JSONFrameSerializer)
    assert isinstance(get_serializer('protobuf'), ProtobufFrameSerializer)


# ─── E4 Telephony serializers ────────────────────────────────────────

def test_telnyx_roundtrip():
    from lvp.telephony import TelnyxSerializer
    s = TelnyxSerializer(stream_sid='abc')
    # inbound media (μ-law) → audio event with pcm
    import base64, audioop
    ulaw = audioop.lin2ulaw(b'\x00\x01' * 80, 2)
    msg = '{"event":"media","media":{"payload":"%s"}}' % base64.b64encode(ulaw).decode()
    out = s.deserialize(msg)
    assert out['type'] == 'audio' and len(out['pcm']) > 0
    # outbound envelope uses stream_id
    import json
    env = json.loads(s.serialize_audio(b'\x00\x01' * 160))
    assert env['event'] == 'media' and env['stream_id'] == 'abc' and env['media']['payload']


def test_plivo_outbound_uses_playaudio():
    from lvp.telephony import PlivoSerializer
    import json
    s = PlivoSerializer(stream_sid='sid1')
    env = json.loads(s.serialize_audio(b'\x00\x01' * 160))
    assert env['event'] == 'playAudio'
    assert env['media']['contentType'] == 'audio/x-mulaw'
    assert env['streamId'] == 'sid1'


def test_exotel_linear_pcm_roundtrip():
    from lvp.telephony import ExotelSerializer
    import base64, json
    s = ExotelSerializer(stream_sid='ex1')
    # Exotel streams raw PCM16 @ 8k (no μ-law)
    pcm8k = b'\x00\x10' * 80
    msg = '{"event":"media","media":{"payload":"%s"}}' % base64.b64encode(pcm8k).decode()
    out = s.deserialize(msg)
    assert out['type'] == 'audio' and len(out['pcm']) > len(pcm8k)   # upsampled 8k→16k
    env = json.loads(s.serialize_audio(b'\x00\x10' * 160))
    assert env['stream_sid'] == 'ex1' and env['media']['payload']


def test_telnyx_start_reads_stream_id():
    from lvp.telephony import TelnyxSerializer
    s = TelnyxSerializer()
    out = s.deserialize('{"event":"start","start":{"stream_id":"zzz"}}')
    assert out == {'type': 'control', 'action': 'start'}
    assert s.stream_sid == 'zzz'
