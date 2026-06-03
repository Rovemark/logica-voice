"""
serializers.py — frame ↔ wire serialization (pluggable).

The transport sends control messages as JSON and audio as raw binary. For lower
overhead on busy links you can swap to a compact binary serializer. This module
defines a small interface plus two implementations:

  - JSONFrameSerializer   : human-readable, the default
  - MsgpackFrameSerializer : compact binary (needs `msgpack`), drop-in alternative

(A Protobuf serializer can be added the same way by implementing FrameSerializer;
msgpack gets ~90% of the size win with zero .proto compilation.)
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


def get_serializer(name='json') -> FrameSerializer:
    name = (name or 'json').lower()
    if name in ('msgpack', 'binary'):
        return MsgpackFrameSerializer()
    return JSONFrameSerializer()
