"""
audio_util.py — shared audio helpers (high-quality resampling).

The pipeline mixes sample rates: STT wants 16 kHz, TTS emits 24 kHz, phone lines are
8 kHz. Naive nearest-neighbor resampling aliases (audible buzz/metallic edge). This uses
soxr (the same VHQ resampler Pipecat uses) when available, falling back to scipy's
polyphase filter, then to nearest-neighbor only as a last resort.

  resample_int16(samples, src_sr, dst_sr) -> np.ndarray[int16]
"""

import numpy as np

try:
    import soxr
    _HAVE_SOXR = True
except Exception:
    _HAVE_SOXR = False

try:
    from scipy.signal import resample_poly
    from math import gcd
    _HAVE_SCIPY = True
except Exception:
    _HAVE_SCIPY = False


def resample_int16(samples, src_sr: int, dst_sr: int):
    """
    Resample a mono int16 numpy array from src_sr to dst_sr. Returns int16.
    Quality: soxr VHQ > scipy polyphase > nearest-neighbor (last resort).
    """
    if src_sr == dst_sr or len(samples) == 0:
        return samples.astype(np.int16, copy=False)

    if _HAVE_SOXR:
        out = soxr.resample(samples.astype(np.float32), src_sr, dst_sr, quality='VHQ')
        return _to_int16(out)

    if _HAVE_SCIPY:
        from math import gcd as _gcd
        g = _gcd(int(src_sr), int(dst_sr))
        up, down = dst_sr // g, src_sr // g
        out = resample_poly(samples.astype(np.float32), up, down)
        return _to_int16(out)

    # last resort: nearest-neighbor (aliases, but never crashes)
    ratio = dst_sr / src_sr
    idx = np.minimum((np.arange(int(len(samples) * ratio)) / ratio).astype(np.int64),
                     len(samples) - 1)
    return samples[idx].astype(np.int16, copy=False)


def _to_int16(float_arr):
    np.clip(float_arr, -32768, 32767, out=float_arr)
    return float_arr.astype(np.int16)
