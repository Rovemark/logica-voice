"""
aggregators.py — stream transformers that sit between stages.

- PatternAggregator : strips paired blocks from the LLM token stream before TTS
                      (e.g. <thinking>…</thinking>, ```code```), so the bot never
                      *speaks* its scratch-pad. Streams the visible text through intact.
- DTMFAggregator    : collects telephony key presses (InputDTMFFrame) into a string and
                      emits a TranscriptionFrame on a terminator key or timeout — so "press
                      1234#" becomes a normal user turn the LLM can act on.
- WordAggregator    : re-emits TranscriptionFrame word timings as WordTimestampFrame events
                      (one per word) for clients that highlight words as they're read.

All generic, no external deps.
"""

import re
import time
import asyncio

from .processor import FrameProcessor, Direction
from .frames import (
    LLMTokenFrame, LLMFullResponseFrame, TranscriptionFrame, WordTimestampFrame,
    InputDTMFFrame, InterruptionFrame,
)


class PatternAggregator(FrameProcessor):
    """
    Removes paired-tag blocks from the LLM token stream while preserving streaming.

    Buffers only as much as needed to decide if we're inside a hidden block. Default hides
    <thinking>…</thinking>. Pass extra (open, close) pairs to hide more (e.g. code fences).
    """

    def __init__(self, pairs=(('<thinking>', '</thinking>'),), name=None):
        super().__init__(name)
        self.pairs = [(o, c) for o, c in pairs]
        self._buf = ''
        self._hiding_close = None   # the close tag we're currently waiting for

    def _max_open_len(self):
        return max((len(o) for o, _ in self.pairs), default=0)

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._buf = ''
            self._hiding_close = None
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, LLMTokenFrame):
            self._buf += frame.text
            await self._drain()
            return
        if isinstance(frame, LLMFullResponseFrame):
            # flush any safe tail (we're not mid-hidden-block)
            if self._hiding_close is None and self._buf:
                visible, self._buf = self._buf, ''
                if visible:
                    await self.push_frame(LLMTokenFrame(text=visible), Direction.DOWNSTREAM)
            self._buf = ''
            self._hiding_close = None
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    async def _drain(self):
        while self._buf:
            if self._hiding_close:
                idx = self._buf.find(self._hiding_close)
                if idx == -1:
                    # still hidden; keep only a tail that could be a partial close tag
                    keep = len(self._hiding_close) - 1
                    self._buf = self._buf[-keep:] if keep > 0 else ''
                    return
                self._buf = self._buf[idx + len(self._hiding_close):]
                self._hiding_close = None
                continue
            # not hiding: find the earliest open tag
            first_pos, close_for = None, None
            for o, c in self.pairs:
                p = self._buf.find(o)
                if p != -1 and (first_pos is None or p < first_pos):
                    first_pos, close_for, open_len = p, c, len(o)
            if first_pos is None:
                # no open tag — but a tag could be split across chunks; hold back a tail
                hold = self._max_open_len() - 1
                if hold > 0 and len(self._buf) > hold:
                    visible, self._buf = self._buf[:-hold], self._buf[-hold:]
                    if visible:
                        await self.push_frame(LLMTokenFrame(text=visible), Direction.DOWNSTREAM)
                return
            if first_pos > 0:
                visible = self._buf[:first_pos]
                await self.push_frame(LLMTokenFrame(text=visible), Direction.DOWNSTREAM)
            self._buf = self._buf[first_pos + open_len:]
            self._hiding_close = close_for


class DTMFAggregator(FrameProcessor):
    """
    Collects InputDTMFFrame digits into a sequence, emitting a TranscriptionFrame when a
    terminator is pressed or after `timeout_secs` of inactivity. Lets a phone keypad drive
    the same LLM turn flow as speech.
    """

    def __init__(self, terminators=('#',), timeout_secs=3.0, prefix='DTMF: ', name=None):
        super().__init__(name)
        self.terminators = set(terminators)
        self.timeout_secs = timeout_secs
        self.prefix = prefix
        self._digits = ''
        self._timer = None

    async def process_frame(self, frame, direction):
        if isinstance(frame, InputDTMFFrame):
            digit = frame.digit
            if digit in self.terminators:
                await self._flush()
            else:
                self._digits += digit
                self._reset_timer()
            # still forward the raw key (telephony layer may want it)
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    def _reset_timer(self):
        if self._timer and not self._timer.done():
            self._timer.cancel()
        self._timer = self._spawn(self._timeout())

    async def _timeout(self):
        try:
            await asyncio.sleep(self.timeout_secs)
            await self._flush()
        except asyncio.CancelledError:
            pass

    async def _flush(self):
        if not self._digits:
            return
        seq, self._digits = self._digits, ''
        await self.push_frame(TranscriptionFrame(text=f'{self.prefix}{seq}'),
                              Direction.DOWNSTREAM)


class WordAggregator(FrameProcessor):
    """
    Fans a TranscriptionFrame's word timings out as individual WordTimestampFrame events
    (passes the TranscriptionFrame through unchanged). No-op when the STT didn't return
    word timings.
    """

    async def process_frame(self, frame, direction):
        if isinstance(frame, TranscriptionFrame) and getattr(frame, 'words', None):
            await self.push_frame(frame, direction)
            for w in frame.words:
                await self.push_frame(
                    WordTimestampFrame(word=w.get('word', ''), time=float(w.get('start', 0.0))),
                    Direction.DOWNSTREAM)
            return
        await super().process_frame(frame, direction)
