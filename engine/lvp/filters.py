"""
filters.py — frame filters (gate what flows through the pipeline).

- WakeCheckFilter   : only let transcriptions through after a wake word ("Astro", "Jarvis")
- STTMuteFilter     : drop input audio while the bot speaks / runs a tool (no self-hearing)
- FrameFilter       : only let allowed frame types pass
- FunctionFilter    : custom predicate
- IdentityFilter    : passthrough (composition/debug)
- NullFilter        : block everything
- GatedProcessor    : hold frames until a gate opens, then release in order

Place a filter anywhere in the chain. Filters never modify frames, only pass/block.
"""

import re
from enum import Enum

from .processor import FrameProcessor, Direction
from .frames import (
    TranscriptionFrame, InterimTranscriptionFrame, SystemFrame,
    AudioInFrame, TTSStartedFrame, TTSStoppedFrame,
    FunctionCallFrame, FunctionCallResultFrame,
)


class STTMuteStrategy(Enum):
    """When to drop incoming audio so the bot doesn't transcribe itself / get barged."""
    ALWAYS_WHILE_BOT_SPEAKS = 'always'              # mute whenever the bot is speaking
    UNTIL_FIRST_BOT_COMPLETE = 'until_first_bot'    # mute until the bot finishes its 1st turn
    FUNCTION_CALL = 'function_call'                 # mute while a tool call runs
    CUSTOM = 'custom'                               # mute when should_mute() returns True


class STTMuteFilter(FrameProcessor):
    """
    Drops AudioInFrame while "muted", per one or more strategies. Place it BEFORE the VAD
    so muted audio reaches neither STT nor barge-in detection — the classic fixes for
    "the bot hears its own greeting" and "a tool result gets interrupted by room noise".

    strategies   : iterable of STTMuteStrategy
    should_mute  : callable() -> bool, used with STTMuteStrategy.CUSTOM
    """

    def __init__(self, strategies=(STTMuteStrategy.ALWAYS_WHILE_BOT_SPEAKS,),
                 should_mute=None, name=None):
        super().__init__(name)
        self.strategies = set(strategies)
        self.should_mute = should_mute
        self._bot_speaking = False
        self._first_bot_done = False
        self._in_function_call = False

    @property
    def muted(self):
        s = self.strategies
        if STTMuteStrategy.CUSTOM in s and self.should_mute and self.should_mute():
            return True
        if STTMuteStrategy.ALWAYS_WHILE_BOT_SPEAKS in s and self._bot_speaking:
            return True
        if STTMuteStrategy.UNTIL_FIRST_BOT_COMPLETE in s and not self._first_bot_done:
            return True
        if STTMuteStrategy.FUNCTION_CALL in s and self._in_function_call:
            return True
        return False

    async def process_frame(self, frame, direction):
        # Track bot/tool state from the frames flowing by (these still pass through).
        if isinstance(frame, TTSStartedFrame):
            self._bot_speaking = True
        elif isinstance(frame, TTSStoppedFrame):
            self._bot_speaking = False
            self._first_bot_done = True
        elif isinstance(frame, FunctionCallFrame):
            self._in_function_call = True
        elif isinstance(frame, FunctionCallResultFrame):
            self._in_function_call = False

        # Drop input audio while muted; everything else (incl. system frames) flows.
        if isinstance(frame, AudioInFrame) and self.muted:
            return
        await super().process_frame(frame, direction)


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


class GatedProcessor(FrameProcessor):
    """
    Holds gated frames in order until a gate opens, then releases them. Useful when a
    downstream stage must wait for something — e.g. don't speak (hold AudioOutFrame) until
    an image-gen tool returns its OutputImageFrame.

    start_open  : initial gate state
    open_when   : predicate(frame) -> bool; when True (on any passing frame), open + flush
    close_when  : predicate(frame) -> bool; when True, close the gate again
    gated_types : only these types are held while closed (None = all data frames)

    System frames always pass immediately. An interruption clears whatever is held.
    """

    def __init__(self, start_open=False, open_when=None, close_when=None,
                 gated_types=None, name=None):
        super().__init__(name)
        self._open = start_open
        self.open_when = open_when
        self.close_when = close_when
        self.gated_types = tuple(gated_types) if gated_types else None
        self._held = []

    async def process_frame(self, frame, direction):
        from .frames import InterruptionFrame
        if isinstance(frame, InterruptionFrame):
            self._held.clear()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, SystemFrame):
            await self.push_frame(frame, direction)
            return

        # gate transitions (evaluated on the frame as it arrives)
        if not self._open and self.open_when and self.open_when(frame):
            self._open = True
            await self.push_frame(frame, direction)
            await self._flush()
            return
        if self._open and self.close_when and self.close_when(frame):
            self._open = False

        gated = self.gated_types is None or isinstance(frame, self.gated_types)
        if self._open or not gated:
            await self.push_frame(frame, direction)
        else:
            self._held.append((frame, direction))

    async def _flush(self):
        held, self._held = self._held, []
        for frame, direction in held:
            await self.push_frame(frame, direction)
