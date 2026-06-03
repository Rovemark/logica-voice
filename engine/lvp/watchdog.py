"""
watchdog.py — detect a stalled pipeline and point at the stage that hung.

The heartbeat (HeartbeatFrame) is injected at the head and travels the whole chain to the
transport at the tail. WatchdogObserver watches each hop: if a heartbeat enters the
pipeline but doesn't reach the tail within `timeout_secs`, something between the last seen
stage and the tail is stuck — and we know which stage it last cleared.

    wd = WatchdogObserver(tail_name='TransportOutput', timeout_secs=5,
                          on_stall=lambda seq, stage: log(f'stalled after {stage}'))
    # add to the Pipeline's observers; call wd.check() periodically (the runner does this
    # right after it sends each heartbeat).
"""

import time

from .processor import BaseObserver
from .frames import HeartbeatFrame


class WatchdogObserver(BaseObserver):
    def __init__(self, tail_name, timeout_secs=5.0, on_stall=None):
        self.tail_name = tail_name
        self.timeout_secs = timeout_secs
        self.on_stall = on_stall
        self._inflight = {}     # seq -> {'t': monotonic_start, 'last': processor_name}
        self._reported = set()

    async def on_push_frame(self, processor, frame, direction):
        if not isinstance(frame, HeartbeatFrame):
            return
        seq = frame.seq
        rec = self._inflight.get(seq)
        if rec is None:
            rec = self._inflight[seq] = {'t': time.monotonic(), 'last': processor.name}
        rec['last'] = processor.name
        if processor.name == self.tail_name:
            # reached the end → this heartbeat completed cleanly
            self._inflight.pop(seq, None)
            self._reported.discard(seq)

    def check(self):
        """Report any heartbeat that hasn't completed within timeout_secs. Idempotent."""
        now = time.monotonic()
        stalls = []
        for seq, rec in list(self._inflight.items()):
            if now - rec['t'] >= self.timeout_secs and seq not in self._reported:
                self._reported.add(seq)
                stalls.append((seq, rec['last']))
        for seq, stage in stalls:
            if self.on_stall:
                try:
                    self.on_stall(seq, stage)
                except Exception:
                    pass
            else:
                print(f'[watchdog] pipeline stalled: heartbeat {seq} stuck after stage '
                      f'"{stage}" (> {self.timeout_secs}s)', flush=True)
        return stalls
