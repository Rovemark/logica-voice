"""
idle_processor.py — user inactivity detection + re-engagement.

UserIdleProcessor watches the conversation; if the user goes quiet for `timeout_secs`
with no new speech, it fires a callback with an escalating retry_count (1st time:
"still there?", 2nd: wrap up, etc). The timer resets whenever the user speaks.

Place it early in the pipeline (right after VAD). The callback can push a TTSSpeak
or end the session — that's up to the app.
"""

import asyncio
import time

from .processor import FrameProcessor, Direction
from .frames import (
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame, AudioOutFrame,
    InterruptionFrame, EndFrame,
)


class UserIdleProcessor(FrameProcessor):
    def __init__(self, callback, timeout_secs=15.0, name=None):
        """
        callback(processor, retry_count) -> awaitable | None
          retry_count starts at 1 and increments each timeout until the user speaks.
        """
        super().__init__(name)
        self.callback = callback
        self.timeout_secs = timeout_secs
        self._retry = 0
        self._last_activity = time.time()
        self._timer = None
        self._bot_speaking = False
        self._closed = False

    async def process_frame(self, frame, direction):
        # Any user speech or bot audio counts as activity
        if isinstance(frame, (UserStartedSpeakingFrame, UserStoppedSpeakingFrame)):
            self._activity()
        elif isinstance(frame, AudioOutFrame):
            self._bot_speaking = True
            self._activity()
        elif isinstance(frame, InterruptionFrame):
            self._activity()
        elif isinstance(frame, EndFrame):
            self._closed = True
            self._stop_timer()

        # keep the idle timer running
        if not self._closed and self._timer is None:
            self._start_timer()

        await super().process_frame(frame, direction)

    def _activity(self):
        self._retry = 0
        self._last_activity = time.time()

    def _start_timer(self):
        self._timer = self._spawn(self._watch())

    def _stop_timer(self):
        self._cancel_tasks()
        self._timer = None

    async def _watch(self):
        try:
            while not self._closed:
                await asyncio.sleep(self.timeout_secs)
                idle = time.time() - self._last_activity
                if idle >= self.timeout_secs:
                    self._retry += 1
                    try:
                        res = self.callback(self, self._retry)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        print(f'[idle] callback error: {e}', flush=True)
                    # avoid tight loop: push activity stamp forward by one window
                    self._last_activity = time.time()
        except asyncio.CancelledError:
            pass

    async def on_end(self):
        self._closed = True
        self._stop_timer()
