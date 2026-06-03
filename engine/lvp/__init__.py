"""
LVP — Logica Voice Pipeline
============================

A frame-based, streaming, full-duplex voice pipeline. Audio flows as frames through a
chain of FrameProcessors — VAD → STT → LLM → SentenceAggregator → TTS → Transport —
with barge-in, semantic turn detection, tools, metrics, and pluggable transports.

100% ours, generic, open-source. Point it at any LLM (LVP_LLM_URL); swap any STT/TTS.

Modules:
  frames        — typed frames (Audio/Text/Transcription/LLM/Tool/Vision/System…)
  processor     — FrameProcessor, Pipeline, BaseObserver
  vad_processor — Silero VAD + smart-turn + barge-in
  smart_turn    — semantic end-of-turn (ONNX, multilingual)
  stt_processor — speech-to-text (+ streaming partials)
  llm_processor — LLM over SSE (+ tools)
  context       — LLMContext (multi-turn memory + tools)
  tools         — ToolRegistry (function calling)
  tts_processor — SentenceAggregator + TTS
  transport     — frames → WebSocket
  transports    — BaseTransport, WebSocket, WebRTC
  telephony     — Twilio/μ-law + DTMF
  serializers   — JSON / Msgpack
  rtvi          — RTVI event protocol
  metrics       — TTFB per stage
  tracing       — OpenTelemetry (optional)
  recording     — AudioBufferProcessor
  audio_filter  — noise suppression
  idle_processor— user idle / re-engagement
  advanced      — ParallelPipeline, ServiceSwitcher
  runner        — wires it all + serves WebSocket
"""

from .frames import (
    Frame, SystemFrame, DataFrame,
    AudioInFrame, AudioOutFrame, TranscriptionFrame, InterimTranscriptionFrame,
    PartialUtteranceFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    LLMTokenFrame, LLMFullResponseFrame, TextSentenceFrame,
    FunctionCallFrame, FunctionCallResultFrame,
    InputImageFrame, UserImageFrame, OutputImageFrame, VisionTextFrame,
    InputDTMFFrame, OutputDTMFFrame, MetricsFrame,
    InterruptionFrame, CancelFrame, ErrorFrame, EndFrame, ControlFrame,
)
from .processor import FrameProcessor, Pipeline, BaseObserver, Direction

__all__ = [
    'Frame', 'SystemFrame', 'DataFrame',
    'AudioInFrame', 'AudioOutFrame', 'TranscriptionFrame', 'InterimTranscriptionFrame',
    'PartialUtteranceFrame', 'UserStartedSpeakingFrame', 'UserStoppedSpeakingFrame',
    'LLMTokenFrame', 'LLMFullResponseFrame', 'TextSentenceFrame',
    'FunctionCallFrame', 'FunctionCallResultFrame',
    'InputImageFrame', 'UserImageFrame', 'OutputImageFrame', 'VisionTextFrame',
    'InputDTMFFrame', 'OutputDTMFFrame', 'MetricsFrame',
    'InterruptionFrame', 'CancelFrame', 'ErrorFrame', 'EndFrame', 'ControlFrame',
    'FrameProcessor', 'Pipeline', 'BaseObserver', 'Direction',
]
