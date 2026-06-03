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
    """
    Base de todo estágio do pipeline.

    Priority model: SystemFrames (Interruption/Cancel/End/Start/Heartbeat…) are handled
    IMMEDIATELY, bypassing any data-frame backlog. DataFrames are processed in order and
    can be paused/resumed (held in a queue while paused). This keeps barge-in and control
    snappy even when a processor is busy or paused.
    """

    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__
        self._next: 'FrameProcessor' = None
        self._prev: 'FrameProcessor' = None
        self._tasks: set = set()
        self._paused = False
        self._data_queue: list = []   # data frames held while paused

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
        Default routing. System frames (high priority) are handled immediately and
        bypass pause; data frames respect pause (queued until resume). Subclasses call
        super().process_frame() then handle their own data frames.
        """
        from .frames import SystemFrame, CancelFrame, PauseFrame, ResumeFrame
        # ── System frames: always immediate, even while paused ──
        if isinstance(frame, (InterruptionFrame, CancelFrame)):
            self._cancel_tasks()
            self._data_queue.clear()   # drop queued data on interruption
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, EndFrame):
            self._cancel_tasks()
            await self.on_end()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, PauseFrame):
            if not frame.target or frame.target == self.name:
                self._paused = True
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, ResumeFrame):
            if not frame.target or frame.target == self.name:
                await self._resume()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, SystemFrame):
            await self.push_frame(frame, direction)
            return
        # ── Data/control frames: respect pause ──
        if self._paused:
            self._data_queue.append((frame, direction))
            return
        await self.push_frame(frame, direction)

    async def pause(self):
        self._paused = True

    async def resume(self):
        await self._resume()

    async def _resume(self):
        self._paused = False
        queued, self._data_queue = self._data_queue, []
        for frame, direction in queued:
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
