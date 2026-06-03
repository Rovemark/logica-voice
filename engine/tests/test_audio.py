"""audio_util resampling + AudioMixer."""

import numpy as np

from conftest import run, pipeline, feed, of_type
from lvp.processor import Direction
from lvp.audio_util import resample_int16
from lvp.audio_mixer import AudioMixer
from lvp.frames import AudioOutFrame, TTSStartedFrame, TTSStoppedFrame


def _tone(sr, hz=440, secs=1.0, amp=12000):
    t = np.arange(int(sr * secs)) / sr
    return (np.sin(2 * np.pi * hz * t) * amp).astype(np.int16)


def test_resample_lengths_and_dtype():
    tone = _tone(24000)
    down = resample_int16(tone, 24000, 16000)
    up = resample_int16(down, 16000, 24000)
    assert down.dtype == np.int16 and up.dtype == np.int16
    assert abs(len(down) - 16000) <= 2
    assert abs(len(up) - 24000) <= 4


def test_resample_preserves_energy():
    tone = _tone(24000)
    down = resample_int16(tone, 24000, 16000)
    rms = lambda x: float(np.sqrt(np.mean(x.astype(np.float32) ** 2)))
    assert 0.85 < rms(down) / rms(tone) < 1.15


def test_resample_noop_same_rate():
    tone = _tone(16000)
    out = resample_int16(tone, 16000, 16000)
    assert np.array_equal(out, tone)


def test_resample_empty():
    out = resample_int16(np.zeros(0, dtype=np.int16), 24000, 16000)
    assert len(out) == 0


def test_mixer_passthrough_without_bed():
    head, sink = pipeline(AudioMixer(bed_path=None))
    pcm = (b'\x10\x00' * 240)
    run(feed(head, [AudioOutFrame(pcm=pcm)]))
    got = of_type(sink.out, AudioOutFrame)
    assert got and got[0].pcm == pcm   # no bed → untouched


def test_mixer_tracks_speaking_state():
    m = AudioMixer(bed_path=None)
    head, sink = pipeline(m)
    run(feed(head, [TTSStartedFrame(), TTSStoppedFrame()]))
    # frames pass through and state toggles cleanly
    assert m._speaking is False
    assert of_type(sink.out, TTSStartedFrame) and of_type(sink.out, TTSStoppedFrame)
