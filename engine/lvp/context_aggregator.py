"""
context_aggregator.py — assemble clean conversational turns + maintain LLMContext.

The batch STT emits one TranscriptionFrame per turn, but a *streaming* STT can emit
several finals as the user talks ("I'd like" … "a coffee" … "please"). Feeding those to
the LLM as-is makes three turns out of one. These aggregators fix that and own the
context bookkeeping (the Pipecat pattern), so the LLM stage doesn't have to.

  UserContextAggregator      : fuse adjacent TranscriptionFrames into one turn (timeout),
                               optionally appending to an LLMContext.
  AssistantContextAggregator : build assistant turns from the LLM stream into the context
                               (for setups where the LLM stage doesn't do its own bookkeeping).

Both are transparent: frames still flow downstream; they just consolidate + record.
"""

import asyncio

from .processor import FrameProcessor, Direction
from .frames import (
    TranscriptionFrame, InterimTranscriptionFrame, LLMTokenFrame, LLMFullResponseFrame,
    InterruptionFrame,
)


class UserContextAggregator(FrameProcessor):
    """
    Fuses TranscriptionFrames that arrive within `aggregation_timeout` of each other into
    a single consolidated TranscriptionFrame. With aggregation_timeout <= 0 it's a
    transparent passthrough (right for batch STT, which already emits one final per turn).
    """

    def __init__(self, context=None, aggregation_timeout=0.0, name=None):
        super().__init__(name)
        self.context = context
        self.aggregation_timeout = aggregation_timeout
        self._parts = []
        self._timer = None

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._cancel_timer()
            self._parts = []
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TranscriptionFrame):
            if self.aggregation_timeout <= 0:
                if self.context:
                    self.context.add_user(frame.text)
                await self.push_frame(frame, direction)
                return
            self._parts.append(frame.text)
            self._reset_timer()
            return   # hold until the gap closes
        await super().process_frame(frame, direction)

    def _cancel_timer(self):
        if self._timer and not self._timer.done():
            self._timer.cancel()
        self._timer = None

    def _reset_timer(self):
        self._cancel_timer()
        self._timer = self._spawn(self._wait_and_flush())

    async def _wait_and_flush(self):
        try:
            await asyncio.sleep(self.aggregation_timeout)
            await self._flush()
        except asyncio.CancelledError:
            pass

    async def _flush(self):
        if not self._parts:
            return
        text = ' '.join(p.strip() for p in self._parts if p.strip()).strip()
        self._parts = []
        if not text:
            return
        if self.context:
            self.context.add_user(text)
        await self.push_frame(TranscriptionFrame(text=text), Direction.DOWNSTREAM)


class AssistantContextAggregator(FrameProcessor):
    """
    Records the assistant's turn into the LLMContext as it streams. Accumulates
    LLMTokenFrame text and commits on LLMFullResponseFrame (or on interruption, committing
    whatever was spoken so far — so the model remembers a half-finished reply). Transparent.
    """

    def __init__(self, context, name=None):
        super().__init__(name)
        self.context = context
        self._buf = ''

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._commit(self._buf)        # remember the partial reply
            self._buf = ''
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, LLMTokenFrame):
            self._buf += frame.text
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, LLMFullResponseFrame):
            self._commit(frame.text or self._buf)
            self._buf = ''
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    def _commit(self, text):
        text = (text or '').strip()
        if text and self.context:
            self.context.add_assistant(text)
