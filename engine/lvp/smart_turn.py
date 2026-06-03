"""
smart_turn.py — Semantic end-of-turn detection (ONNX, local, multilingual incl. PT-BR).

Standalone reimplementation of the smart-turn-v3 approach: a tiny Whisper-encoder
classifier that looks at the last 8 s of audio and predicts whether the speaker has
*actually finished their turn* — not just "is there silence right now" (that's the VAD's
job), but "does this sound complete?" ("I'd like a…" [pause] is NOT complete, even with
250 ms of silence).

Model: pipecat-ai/smart-turn-v3 (8 MB int8 ONNX, 23 languages, ~15-40 ms CPU on M-series).
Runs with onnxruntime + numpy only — no torch, no transformers.

Usage (orchestration lives in vad_processor.py):
    det = SmartTurnDetector()                  # lazy-downloads the model on first use
    complete, prob = det.is_turn_complete(pcm_f32_16k)   # pcm float32 [-1,1] @ 16 kHz
"""

import os
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

_SR = 16000
_N_FFT = 400
_HOP = 160
_N_MELS = 80
_CHUNK_SECONDS = 8
_N_SAMPLES = _SR * _CHUNK_SECONDS          # 128000
_MEL_FLOOR = 1e-10
_NORM_EPS = 1e-7

_MODEL_REPO = os.environ.get('LVP_SMART_TURN_REPO', 'pipecat-ai/smart-turn-v3')
_MODEL_FILE = os.environ.get('LVP_SMART_TURN_FILE', 'smart-turn-v3.2-cpu.onnx')


# ─── Whisper log-mel (numpy only — bit-compatible with the reference) ───────

def _hz_to_mel(freq):
    freq = np.atleast_1d(np.asarray(freq, dtype=np.float64))
    mels = 3.0 * freq / 200.0
    log_region = freq >= 1000.0
    mels[log_region] = 15.0 + np.log(freq[log_region] / 1000.0) * (27.0 / np.log(6.4))
    return mels


def _mel_to_hz(mels):
    mels = np.atleast_1d(np.asarray(mels, dtype=np.float64))
    freq = 200.0 * mels / 3.0
    log_region = mels >= 15.0
    freq[log_region] = 1000.0 * np.exp((np.log(6.4) / 27.0) * (mels[log_region] - 15.0))
    return freq


def _build_mel_filters():
    n_bins = _N_FFT // 2 + 1
    mel_min = float(_hz_to_mel([0.0])[0])
    mel_max = float(_hz_to_mel([_SR / 2.0])[0])
    mel_freqs = np.linspace(mel_min, mel_max, _N_MELS + 2)
    filter_freqs = _mel_to_hz(mel_freqs)
    fft_freqs = np.linspace(0, _SR // 2, n_bins)
    diff = np.diff(filter_freqs)
    slopes = np.expand_dims(filter_freqs, 0) - np.expand_dims(fft_freqs, 1)
    down = -slopes[:, :-2] / diff[:-1]
    up = slopes[:, 2:] / diff[1:]
    mel = np.maximum(0.0, np.minimum(down, up))
    enorm = 2.0 / (filter_freqs[2:_N_MELS + 2] - filter_freqs[:_N_MELS])
    mel *= np.expand_dims(enorm, 0)
    return mel


_HANN = np.hanning(_N_FFT + 1)[:-1]
_MEL_FILTERS = _build_mel_filters()


def _power_spec(x):
    pad = _N_FFT // 2
    padded = np.pad(x.astype(np.float64), (pad, pad), mode="reflect")
    win = _HANN.astype(np.float64)
    windows = sliding_window_view(padded, _N_FFT)[::_HOP]
    spec = np.fft.rfft(windows * win, axis=-1)
    return (np.abs(spec) ** 2).T


def _compute_log_mel(audio, do_normalize=True):
    x = np.asarray(audio, dtype=np.float32)
    if x.size < _N_SAMPLES:
        x = np.pad(x, (0, _N_SAMPLES - x.size))
    elif x.size > _N_SAMPLES:
        x = x[:_N_SAMPLES]
    if do_normalize:
        x = (x - x.mean()) / np.sqrt(x.var() + _NORM_EPS)
    mags = _power_spec(x)
    mel = np.maximum(_MEL_FLOOR, _MEL_FILTERS.T @ mags)
    log = np.log10(mel)[:, :-1]
    log = np.maximum(log, log.max() - 8.0)
    log = (log + 4.0) / 4.0
    return log.astype(np.float32)


# ─── Detector ───────────────────────────────────────────────────────────────

class SmartTurnDetector:
    def __init__(self, model_path=None, cpu_count=1, threshold=0.5):
        try:
            import onnxruntime as ort
        except ImportError:
            raise RuntimeError("onnxruntime não instalado. pip install onnxruntime")
        if model_path is None:
            from huggingface_hub import hf_hub_download
            model_path = hf_hub_download(repo_id=_MODEL_REPO, filename=_MODEL_FILE)
        self.threshold = threshold
        so = ort.SessionOptions()
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.inter_op_num_threads = 1
        so.intra_op_num_threads = cpu_count
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, sess_options=so)

    def is_turn_complete(self, audio_pcm_16khz):
        """
        audio_pcm_16khz: np.ndarray float32 in [-1, 1] @ 16 kHz mono
                         (int16 → x.astype(np.float32) / 32768.0)
        Returns (complete: bool, probability: float).
        Pads/truncates to the LAST 8 s (the end of the turn is what matters).
        """
        audio = np.asarray(audio_pcm_16khz, dtype=np.float32)
        if len(audio) > _N_SAMPLES:
            audio = audio[-_N_SAMPLES:]
        elif len(audio) < _N_SAMPLES:
            audio = np.pad(audio, (_N_SAMPLES - len(audio), 0))  # pad at the START
        log_mel = _compute_log_mel(audio, do_normalize=True)
        input_features = np.expand_dims(log_mel, axis=0)         # (1, 80, 800)
        outputs = self.session.run(None, {"input_features": input_features})
        probability = float(outputs[0][0].item())               # already sigmoid
        return probability > self.threshold, probability
