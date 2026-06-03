"""
sync.py — Producer/Consumer: move frames between separate pipelines.

Sometimes one pipeline produces a frame another pipeline needs (e.g. a transcription
pipeline feeding a logging/analytics pipeline, or a parallel branch sharing audio). A
ProducerProcessor watches for matching frames and copies them into one or more connected
ConsumerProcessors, which re-inject them downstream in their own pipeline.

  producer = ProducerProcessor(filter=lambda f: isinstance(f, TranscriptionFrame))
  consumer = ConsumerProcessor()
  producer.connect(consumer)

Generic, no external deps. System frames always pass through the producer untouched.
"""

import asyncio

from .processor import FrameProcessor, Direction
from .frames import SystemFrame, StartFrame, EndFrame


class ProducerProcessor(FrameProcessor):
    """
    Copies frames matching `filter` into every connected consumer's queue.

    filter      : predicate(frame) -> bool (which frames to forward)
    transform   : optional frame -> frame applied before forwarding
    passthrough : if True, the matched frame also continues down THIS pipeline
    """

    def __init__(self, filter=None, transform=None, passthrough=True, name=None):
        super().__init__(name)
        self.filter = filter or (lambda f: True)
        self.transform = transform
        self.passthrough = passthrough
        self._consumers = []

    def connect(self, consumer):
        self._consumers.append(consumer)
        return consumer

    async def process_frame(self, frame, direction):
        if isinstance(frame, SystemFrame):
            await self.push_frame(frame, direction)   # control flows unchanged
            return
        try:
            matched = self.filter(frame)
        except Exception:
            matched = False
        if matched:
            out = self.transform(frame) if self.transform else frame
            for c in self._consumers:
                c._queue.put_nowait(out)
                c._ensure_worker()   # wake the consumer's drain loop (we're in a running loop)
            if not self.passthrough:
                return
        await super().process_frame(frame, direction)


class ConsumerProcessor(FrameProcessor):
    """
    Drains frames pushed by connected producers and injects them downstream into its own
    pipeline. A background worker starts on the first StartFrame (or first frame seen) and
    stops on EndFrame.
    """

    def __init__(self, direction=Direction.DOWNSTREAM, name=None):
        super().__init__(name)
        self._queue = asyncio.Queue()
        self._inject_dir = direction
        self._worker = None

    def _ensure_worker(self):
        if self._worker is None or self._worker.done():
            self._worker = self._spawn(self._drain())

    async def _drain(self):
        try:
            while True:
                frame = await self._queue.get()
                await self.push_frame(frame, self._inject_dir)
        except asyncio.CancelledError:
            raise

    async def process_frame(self, frame, direction):
        if isinstance(frame, StartFrame):
            self._ensure_worker()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, EndFrame):
            self._cancel_tasks()
            await self.push_frame(frame, direction)
            return
        # start lazily even if no StartFrame was sent
        self._ensure_worker()
        await super().process_frame(frame, direction)
