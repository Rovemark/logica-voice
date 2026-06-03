"""
filters.py — frame filters (gate what flows through the pipeline).

- WakeCheckFilter   : only let transcriptions through after a wake word ("Astro", "Jarvis")
- FrameFilter       : only let allowed frame types pass
- FunctionFilter    : custom predicate
- IdentityFilter    : passthrough (composition/debug)
- NullFilter        : block everything

Place a filter anywhere in the chain. Filters never modify frames, only pass/block.
"""

import re

from .processor import FrameProcessor, Direction
from .frames import TranscriptionFrame, InterimTranscriptionFrame, SystemFrame


class WakeCheckFilter(FrameProcessor):
    """
    Gates the conversation behind a wake word. Until the user says one of `wake_words`,
    transcriptions are dropped. After a wake, stays awake for `keepalive_secs` of
    activity (each new turn resets the timer). System frames always pass.
    """

    def __init__(self, wake_words=('astro', 'jarvis'), keepalive_secs=30.0, name=None):
        super().__init__(name)
        self.wake_words = [w.lower() for w in wake_words]
        self.keepalive_secs = keepalive_secs
        self._awake_until = 0.0
        self._pattern = re.compile('|'.join(re.escape(w) for w in self.wake_words), re.I)

    async def process_frame(self, frame, direction):
        if isinstance(frame, SystemFrame):
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            import time
            now = time.time()
            if self._pattern.search(frame.text or ''):
                self._awake_until = now + self.keepalive_secs
                # strip the wake word from the text before passing on
                cleaned = self._pattern.sub('', frame.text).strip(' ,.!?')
                if cleaned:
                    frame = type(frame)(text=cleaned)
                else:
                    return  # wake word only — wait for the actual request
            elif now >= self._awake_until:
                return  # asleep — drop
            else:
                self._awake_until = now + self.keepalive_secs  # stay awake
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)


class FrameFilter(FrameProcessor):
    """Only let the allowed frame types pass (system frames always pass)."""

    def __init__(self, allowed_types, name=None):
        super().__init__(name)
        self.allowed = tuple(allowed_types)

    async def process_frame(self, frame, direction):
        if isinstance(frame, SystemFrame) or isinstance(frame, self.allowed):
            await self.push_frame(frame, direction)


class FunctionFilter(FrameProcessor):
    """Pass a frame only if predicate(frame) is True (system frames always pass)."""

    def __init__(self, predicate, name=None):
        super().__init__(name)
        self.predicate = predicate

    async def process_frame(self, frame, direction):
        if isinstance(frame, SystemFrame) or self.predicate(frame):
            await self.push_frame(frame, direction)


class IdentityFilter(FrameProcessor):
    """Passthrough — useful for composition or debugging."""

    async def process_frame(self, frame, direction):
        await self.push_frame(frame, direction)


class NullFilter(FrameProcessor):
    """Block everything except system frames."""

    async def process_frame(self, frame, direction):
        if isinstance(frame, SystemFrame):
            await self.push_frame(frame, direction)
