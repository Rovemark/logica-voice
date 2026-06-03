"""
processor.py — FrameProcessor base + Pipeline runner.

FrameProcessor: unidade que recebe frames, faz algo, e empurra frames pro próximo.
Pipeline: encadeia processors e roteia frames entre eles.

Design:
  - Cada processor tem push_frame(frame, direction) — manda pro vizinho.
  - DOWNSTREAM (mic→speaker) é o fluxo normal.
  - InterruptionFrame propaga DOWNSTREAM cancelando tasks em curso (barge-in).
  - Processors rodam async; tasks pesadas (STT, LLM, TTS) usam asyncio.Task que
    podem ser canceladas na interrupção.
"""

import asyncio
from enum import Enum
from .frames import Frame, InterruptionFrame, EndFrame, ErrorFrame


class Direction(Enum):
    DOWNSTREAM = 1   # mic → speaker (fluxo principal)
    UPSTREAM = 2     # speaker → mic (controle/interrupção)


class FrameProcessor:
    """Base de todo estágio do pipeline."""

    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__
        self._next: 'FrameProcessor' = None
        self._prev: 'FrameProcessor' = None
        self._tasks: set = set()

    # ─── Encadeamento ────────────────────────────────────────────────
    def link(self, nxt: 'FrameProcessor'):
        self._next = nxt
        nxt._prev = self
        return nxt

    # ─── Push pro vizinho ────────────────────────────────────────────
    async def push_frame(self, frame: Frame, direction: Direction = Direction.DOWNSTREAM):
        target = self._next if direction == Direction.DOWNSTREAM else self._prev
        if target is not None:
            await target.process_frame(frame, direction)

    # ─── Recebe frame — override no subclasse ────────────────────────
    async def process_frame(self, frame: Frame, direction: Direction):
        """
        Default: interrupção cancela tasks locais e propaga; resto repassa.
        Subclasses chamam super().process_frame() e depois tratam seus frames.
        """
        if isinstance(frame, InterruptionFrame):
            self._cancel_tasks()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, EndFrame):
            self._cancel_tasks()
            await self.on_end()
            await self.push_frame(frame, direction)
            return
        # Default: repassa
        await self.push_frame(frame, direction)

    # ─── Task helper (cancelável na interrupção) ─────────────────────
    def _spawn(self, coro):
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _cancel_tasks(self):
        for t in list(self._tasks):
            if not t.done():
                t.cancel()
        self._tasks.clear()

    async def on_end(self):
        """Override pra cleanup."""
        pass


class Pipeline:
    """Encadeia processors e injeta frames no topo (downstream)."""

    def __init__(self, processors: list):
        self.processors = processors
        for a, b in zip(processors, processors[1:]):
            a.link(b)
        self.head = processors[0]
        self.tail = processors[-1]

    async def push(self, frame: Frame, direction: Direction = Direction.DOWNSTREAM):
        """Injeta um frame. DOWNSTREAM entra pela cabeça; UPSTREAM pela cauda."""
        if direction == Direction.DOWNSTREAM:
            await self.head.process_frame(frame, direction)
        else:
            await self.tail.process_frame(frame, direction)

    async def interrupt(self):
        """Barge-in: injeta InterruptionFrame downstream (cancela tudo em curso)."""
        await self.head.process_frame(InterruptionFrame(), Direction.DOWNSTREAM)

    async def end(self):
        await self.head.process_frame(EndFrame(), Direction.DOWNSTREAM)
