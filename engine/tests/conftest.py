"""
Shared test helpers for the LVP engine suite.

We avoid the pytest-asyncio plugin: each async test calls `run(coro())`. A `Sink`
processor collects frames so tests can assert on what flowed downstream, and
`pipeline(...)` wires a chain ending in a Sink.

The torch-backed VAD test is gated with importorskip, so the core suite runs fast in CI
without downloading models; the VAD test runs locally where torch/silero are installed.
"""

import os
import sys
import asyncio

# Make `import lvp` work when pytest runs from the engine dir or repo root.
_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)

import pytest

from lvp.processor import FrameProcessor, Pipeline, Direction


def run(coro):
    return asyncio.run(coro)


class Sink(FrameProcessor):
    """Collects every frame it sees (and passes it on)."""

    def __init__(self):
        super().__init__()
        self.out = []

    async def process_frame(self, frame, direction):
        self.out.append(frame)
        await self.push_frame(frame, direction)


def pipeline(*processors):
    """Wire processors + a trailing Sink. Returns (head, sink)."""
    sink = Sink()
    chain = list(processors) + [sink]
    Pipeline(chain)
    return chain[0], sink


async def feed(head, frames, direction=Direction.DOWNSTREAM):
    for f in frames:
        await head.process_frame(f, direction)


def of_type(frames, *types):
    return [f for f in frames if isinstance(f, types)]


@pytest.fixture
def Direction_():
    return Direction
