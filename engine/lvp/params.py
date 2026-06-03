"""
params.py — PipelineParams: one place for the pipeline's global switches.

Instead of threading a dozen booleans through the runner, bundle them. The runner reads
a PipelineParams to decide whether barge-in is on, how the turn closes, whether metrics /
heartbeat run, etc. `from_env()` builds one from the LVP_* environment so deployments stay
config-driven.
"""

import os
from dataclasses import dataclass, field


@dataclass
class PipelineParams:
    # Conversation behavior
    allow_interruptions: bool = True        # can the user barge in over the bot?
    silence_gap_ms: int = 250               # silence that closes a turn
    smart_turn: bool = False                # ML semantic end-of-turn
    hard_stop_secs: float = 3.0             # fallback turn cutoff

    # VAD robustness
    vad_start_secs: float = 0.0             # onset confirmation (reject clicks)
    vad_min_volume: float = 0.0             # volume gate (reject steady noise)

    # STT streaming
    stt_partial_ms: int = 0                 # emit interim transcriptions every N ms

    # Observability
    enable_metrics: bool = True
    enable_rtvi: bool = False
    enable_tracing: bool = False
    heartbeat_secs: float = 0.0             # 0 = off
    watchdog_secs: float = 0.0              # 0 = off

    # Audio
    echo_tail_ms: int = 800
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls):
        b = lambda k, d: os.environ.get(k, d).lower() in ('1', 'true', 'yes')
        return cls(
            allow_interruptions=b('LVP_ALLOW_INTERRUPTIONS', 'true'),
            silence_gap_ms=int(os.environ.get('LVP_SILENCE_GAP_MS', '250')),
            smart_turn=b('LVP_SMART_TURN', 'false'),
            hard_stop_secs=float(os.environ.get('LVP_HARD_STOP_SECS', '3.0')),
            vad_start_secs=float(os.environ.get('LVP_VAD_START_SECS', '0')),
            vad_min_volume=float(os.environ.get('LVP_VAD_MIN_VOLUME', '0')),
            stt_partial_ms=int(os.environ.get('LVP_STT_PARTIAL_MS', '0')),
            enable_metrics=b('LVP_METRICS', 'true'),
            enable_rtvi=b('LVP_RTVI', 'false'),
            enable_tracing=b('LVP_TRACING', 'false'),
            heartbeat_secs=float(os.environ.get('LVP_HEARTBEAT_SECS', '0')),
            watchdog_secs=float(os.environ.get('LVP_WATCHDOG_SECS', '0')),
            echo_tail_ms=int(os.environ.get('LVP_ECHO_TAIL_MS', '800')),
        )
