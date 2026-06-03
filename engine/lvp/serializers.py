"""
serializers.py — frame ↔ wire serialization (pluggable).

The transport sends control messages as JSON and audio as raw binary. For lower
overhead on busy links you can swap to a compact binary serializer. This module
defines a small interface plus three implementations:

  - JSONFrameSerializer     : human-readable, the default
  - MsgpackFrameSerializer  : compact binary (needs `msgpack`), drop-in alternative
  - ProtobufFrameSerializer : compact binary (needs `protobuf`), schema built in-process
                              at runtime — no .proto file, no protoc step
"""

import json


class FrameSerializer:
    """Serialize an event dict → bytes/str and back. Override both methods."""
    media_type = 'text'   # 'text' or 'binary'

    def serialize(self, event: dict):
        raise NotImplementedError

    def deserialize(self, data):
        raise NotImplementedError


class JSONFrameSerializer(FrameSerializer):
    media_type = 'text'

    def serialize(self, event: dict) -> str:
        return json.dumps(event, ensure_ascii=False)

    def deserialize(self, data):
        if isinstance(data, (bytes, bytearray)):
            data = data.decode('utf-8', errors='ignore')
        return json.loads(data)


class MsgpackFrameSerializer(FrameSerializer):
    media_type = 'binary'

    def __init__(self):
        import msgpack  # raises if not installed
        self._mp = msgpack

    def serialize(self, event: dict) -> bytes:
        return self._mp.packb(event, use_bin_type=True)

    def deserialize(self, data):
        return self._mp.unpackb(data, raw=False)


class ProtobufFrameSerializer(FrameSerializer):
    """
    Compact binary serialization via protobuf, with the message schema built at runtime
    in a private DescriptorPool — so there's no .proto file to ship and no protoc build
    step. Audio rides as raw `bytes` (no base64 inflation); any non-standard event keys
    are JSON-packed into a catch-all field.
    """
    media_type = 'binary'

    # schema: type=1(str) audio=2(bytes) text=3(str) sample_rate=4(int32) json=5(str)
    _KNOWN = {'type', 'pcm', 'text', 'sample_rate'}

    def __init__(self):
        self._Frame = self._build_message_class()

    @staticmethod
    def _build_message_class():
        from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
        F = descriptor_pb2.FieldDescriptorProto
        fdp = descriptor_pb2.FileDescriptorProto()
        fdp.name = 'lvp_frame.proto'
        fdp.package = 'lvp'
        fdp.syntax = 'proto3'
        m = fdp.message_type.add()
        m.name = 'LVPFrame'
        for name, num, ftype in (
            ('type', 1, F.TYPE_STRING), ('audio', 2, F.TYPE_BYTES),
            ('text', 3, F.TYPE_STRING), ('sample_rate', 4, F.TYPE_INT32),
            ('json', 5, F.TYPE_STRING),
        ):
            f = m.field.add()
            f.name, f.number, f.label, f.type = name, num, F.LABEL_OPTIONAL, ftype
        pool = descriptor_pool.DescriptorPool()      # private pool — no global clashes
        file_desc = pool.Add(fdp)
        return message_factory.GetMessageClass(file_desc.message_types_by_name['LVPFrame'])

    def serialize(self, event: dict) -> bytes:
        msg = self._Frame()
        if event.get('type'):
            msg.type = str(event['type'])
        if event.get('pcm'):
            msg.audio = bytes(event['pcm'])
        if event.get('text'):
            msg.text = str(event['text'])
        if event.get('sample_rate'):
            msg.sample_rate = int(event['sample_rate'])
        extra = {k: v for k, v in event.items() if k not in self._KNOWN}
        if extra:
            msg.json = json.dumps(extra, ensure_ascii=False)
        return msg.SerializeToString()

    def deserialize(self, data) -> dict:
        msg = self._Frame()
        msg.ParseFromString(bytes(data))
        out = {}
        if msg.type:
            out['type'] = msg.type
        if msg.audio:
            out['pcm'] = bytes(msg.audio)
        if msg.text:
            out['text'] = msg.text
        if msg.sample_rate:
            out['sample_rate'] = msg.sample_rate
        if msg.json:
            try:
                out.update(json.loads(msg.json))
            except Exception:
                pass
        return out


def get_serializer(name='json') -> FrameSerializer:
    name = (name or 'json').lower()
    if name in ('msgpack', 'binary'):
        return MsgpackFrameSerializer()
    if name in ('protobuf', 'proto', 'pb'):
        return ProtobufFrameSerializer()
    return JSONFrameSerializer()
