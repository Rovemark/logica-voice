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
        # Notify observers (metrics, RTVI, logging) before routing.
        for obs in getattr(self, '_observers', ()):  # _observers set by Pipeline
            try:
                await obs.on_push_frame(self, frame, direction)
            except Exception:
                pass
        target = self._next if direction == Direction.DOWNSTREAM else self._prev
        if target is not None:
            await target.process_frame(frame, direction)

    # ─── Recebe frame — override no subclasse ────────────────────────
    async def process_frame(self, frame: Frame, direction: Direction):
        """
        Default routing. System frames (Interruption/Cancel/End/Error) are high
        priority: they cancel in-flight work and propagate immediately, so barge-in
        and shutdown are never stuck behind a backlog of audio/text data frames.
        Subclasses call super().process_frame() then handle their own data frames.
        """
        from .frames import SystemFrame, CancelFrame  # local import (avoid cycle)
        if isinstance(frame, (InterruptionFrame, CancelFrame)):
            self._cancel_tasks()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, EndFrame):
            self._cancel_tasks()
            await self.on_end()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, SystemFrame):
            # Other system frames (e.g. ErrorFrame): propagate immediately, don't cancel.
            await self.push_frame(frame, direction)
            return
        # Default: repassa data/control frames
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


class BaseObserver:
    """
    Observa frames trafegando no pipeline (sem alterá-los). Base pra métricas,
    RTVI, logging. Override on_push_frame.
    """
    async def on_push_frame(self, processor: 'FrameProcessor', frame: Frame, direction: Direction):
        pass


class Pipeline:
    """Encadeia processors e injeta frames no topo (downstream)."""

    def __init__(self, processors: list, observers: list = None):
        self.processors = processors
        self.observers = observers or []
        for a, b in zip(processors, processors[1:]):
            a.link(b)
        # injeta observers em todos os processors
        for p in processors:
            p._observers = self.observers
        self.head = processors[0]
        self.tail = processors[-1]

    def add_observer(self, obs: BaseObserver):
        self.observers.append(obs)

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
