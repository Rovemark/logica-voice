"""
advanced.py — ParallelPipeline + ServiceSwitcher.

ParallelPipeline: fan a frame out to several branches concurrently and merge their
outputs downstream (e.g. run two LLMs and pick the fastest, or audio + vision in
parallel). Lifecycle frames (End/Cancel/Interruption) sync across all branches.

ServiceSwitcher: wrap N interchangeable processors (e.g. primary TTS + fallback TTS)
and route to the active one, switching on failure or by command — runtime failover.
"""

from .processor import FrameProcessor, Direction
from .frames import SystemFrame, ErrorFrame


class ParallelPipeline(FrameProcessor):
    """
    Runs `branches` (each a list of processors) concurrently. A frame entering the
    ParallelPipeline is pushed into every branch; each branch's tail forwards
    downstream. System frames go to all branches.
    """

    def __init__(self, branches: list, name=None):
        super().__init__(name)
        from .processor import Pipeline
        self._pipelines = [Pipeline(b) for b in branches]
        # each branch tail forwards to THIS processor's next
        for p in self._pipelines:
            p.tail._next = None  # we re-route via _forward

    async def process_frame(self, frame, direction):
        if direction == Direction.DOWNSTREAM:
            # fan out to every branch head
            for p in self._pipelines:
                # bridge: branch tail pushes back into our downstream
                p.tail._next = self._next
                await p.head.process_frame(frame, direction)
        else:
            await super().process_frame(frame, direction)


class ServiceSwitcher(FrameProcessor):
    """
    Holds interchangeable processors and routes to the active one. On ErrorFrame from
    the active service, advances to the next (failover). switch(i) sets it manually.
    """

    def __init__(self, services: list, name=None):
        super().__init__(name)
        assert services, "ServiceSwitcher needs at least one service"
        self.services = services
        self.active = 0
        # link active service's output to our next
        self._wire()

    def _wire(self):
        svc = self.services[self.active]
        svc._next = self._next
        svc._prev = self

    def switch(self, index):
        if 0 <= index < len(self.services):
            self.active = index
            self._wire()

    def failover(self):
        if self.active + 1 < len(self.services):
            self.switch(self.active + 1)
            return True
        return False

    async def process_frame(self, frame, direction):
        if isinstance(frame, ErrorFrame) and direction == Direction.UPSTREAM:
            if self.failover():
                print(f'[switcher] failover → service #{self.active}', flush=True)
                return
        if direction == Direction.DOWNSTREAM and not isinstance(frame, SystemFrame):
            # route data frames into the active service
            self.services[self.active]._next = self._next
            await self.services[self.active].process_frame(frame, direction)
            return
        await super().process_frame(frame, direction)
