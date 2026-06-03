"""
VAD 4-state machine. Needs torch + silero_vad (heavy), so it's gated with importorskip:
it runs locally where the model is installed, and is skipped in the light CI job.

We monkeypatch `_is_speech` with a scripted boolean sequence so transitions are
deterministic (no real audio / model inference needed).
"""

import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("silero_vad")

from conftest import run, pipeline, of_type   # noqa: E402
from lvp.processor import Direction            # noqa: E402
from lvp.vad_processor import VADProcessor, VADState, VAD_FRAME_SIZE   # noqa: E402
from lvp.frames import AudioInFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame  # noqa: E402

CHUNK = np.zeros(VAD_FRAME_SIZE, dtype=np.int16).tobytes()


def _run_seq(vad, speech_seq):
    """Feed len(speech_seq) frames; _is_speech returns the scripted booleans."""
    it = iter(speech_seq)
    vad._is_speech = lambda c: next(it, False)
    head, sink = pipeline(vad)

    async def go():
        for _ in speech_seq:
            await head.process_frame(AudioInFrame(pcm=CHUNK), Direction.DOWNSTREAM)
    run(go())
    return sink


def _vad(**kw):
    return VADProcessor(silence_gap_ms=64, min_utterance_ms=0, **kw)


def test_immediate_onset_speaks_and_closes():
    sink = _run_seq(_vad(start_secs=0.0), [True, True, True, False, False, False])
    assert len(of_type(sink.out, UserStartedSpeakingFrame)) == 1
    assert len(of_type(sink.out, UserStoppedSpeakingFrame)) == 1


def test_false_start_rejected():
    vad = _vad(start_secs=0.09)   # needs ~3 consecutive voice frames
    sink = _run_seq(vad, [True, False, False, False])
    assert of_type(sink.out, UserStartedSpeakingFrame) == []
    assert vad._state == VADState.QUIET


def test_confirmed_onset_speaks():
    sink = _run_seq(_vad(start_secs=0.09), [True, True, True, True, False, False, False])
    assert len(of_type(sink.out, UserStartedSpeakingFrame)) == 1
    assert len(of_type(sink.out, UserStoppedSpeakingFrame)) == 1


def test_brief_pause_does_not_split_turn():
    # voice, 1 silent frame (< gap), voice again → single turn
    sink = _run_seq(_vad(start_secs=0.0), [True, True, False, True, True, False, False])
    assert len(of_type(sink.out, UserStartedSpeakingFrame)) == 1
    assert len(of_type(sink.out, UserStoppedSpeakingFrame)) == 1


def test_min_volume_gate_rejects_quiet():
    vad = _vad(min_volume=0.5)
    quiet = np.zeros(VAD_FRAME_SIZE, dtype=np.int16)
    assert vad._is_speech(quiet) is False   # rms 0 < 0.5 → rejected before the model


# ─── barge-in policy (allow_interruptions / InterruptionStrategy) ─────

from lvp.frames import InterruptionFrame                  # noqa: E402
from lvp.interruptions import MinSpeechDurationStrategy    # noqa: E402


def test_allow_interruptions_false_never_barges():
    vad = _vad(start_secs=0.0, allow_interruptions=False)
    vad._bot_speaking = lambda: True            # bot is talking
    sink = _run_seq(vad, [True, True, True])    # user talks over it
    assert of_type(sink.out, InterruptionFrame) == []   # no barge-in


def test_min_speech_duration_strategy_delays_barge():
    # require ~96ms (3 frames @ ~32ms) of sustained voice before interrupting
    vad = _vad(start_secs=0.0, interruption_strategy=MinSpeechDurationStrategy(min_ms=90))
    vad._bot_speaking = lambda: True
    sink = _run_seq(vad, [True, True, True, True])
    ints = of_type(sink.out, InterruptionFrame)
    assert len(ints) == 1   # fired once, only after enough sustained speech
