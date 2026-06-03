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
  filters       — WakeCheckFilter / STTMuteFilter / GatedProcessor + frame gates
  aggregators   — PatternAggregator / DTMFAggregator / WordAggregator
  context_aggregator — User/Assistant turn aggregation into LLMContext
  interruptions — barge-in strategies (min speech duration / min words)
  transcript    — structured running transcript + update events
  params        — PipelineParams (global switches)
  watchdog      — stalled-pipeline detection via heartbeat round-trip
  audio_mixer   — background music/hold bed
  memory        — LongTermMemory (mem0 / HTTP / in-proc)
  sync          — Producer/Consumer (cross-pipeline frames)
  streaming_stt — WebSocket streaming STT (interim real)
  streaming_tts — WebSocket token-streaming TTS
  llm_adapters  — direct Anthropic / Gemini (native tools)
  serializers   — JSON / Msgpack / Protobuf frame serialization
  telephony     — Twilio / Telnyx / Plivo / Exotel + DTMF
  runner        — wires it all + serves WebSocket

Note: heavyweight processors (VAD/STT/TTS/LLM, which pull torch/onnx/aiohttp) are imported
from their submodules on demand — e.g. `from lvp.vad_processor import VADProcessor` — to keep
`import lvp` light. This module re-exports only frames, core, and the dependency-light helpers.
"""

from .frames import (
    Frame, SystemFrame, DataFrame,
    AudioInFrame, AudioOutFrame, TranscriptionFrame, InterimTranscriptionFrame,
    PartialUtteranceFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    LLMTokenFrame, LLMFullResponseFrame, TextSentenceFrame, WordTimestampFrame,
    FunctionCallFrame, FunctionCallResultFrame,
    InputImageFrame, UserImageFrame, OutputImageFrame, VisionTextFrame,
    InputDTMFFrame, OutputDTMFFrame, MetricsFrame,
    InterruptionFrame, CancelFrame, ErrorFrame, EndFrame, ControlFrame,
    StartFrame, HeartbeatFrame, TTSStartedFrame, TTSStoppedFrame, PauseFrame, ResumeFrame,
    TranscriptionUpdateFrame,
)
from .processor import FrameProcessor, Pipeline, BaseObserver, Direction
from .context import LLMContext
from .tools import ToolRegistry
from .filters import (
    WakeCheckFilter, FrameFilter, FunctionFilter, IdentityFilter, NullFilter,
    STTMuteFilter, STTMuteStrategy, GatedProcessor,
)
from .aggregators import PatternAggregator, DTMFAggregator, WordAggregator
from .context_aggregator import UserContextAggregator, AssistantContextAggregator
from .interruptions import (
    InterruptionStrategy, AlwaysInterruptStrategy,
    MinSpeechDurationStrategy, MinWordsInterruptionStrategy,
)
from .transcript import TranscriptProcessor
from .params import PipelineParams
from .watchdog import WatchdogObserver
from .audio_mixer import AudioMixer
from .memory import LongTermMemory
from .sync import ProducerProcessor, ConsumerProcessor

__all__ = [
    'Frame', 'SystemFrame', 'DataFrame',
    'AudioInFrame', 'AudioOutFrame', 'TranscriptionFrame', 'InterimTranscriptionFrame',
    'PartialUtteranceFrame', 'UserStartedSpeakingFrame', 'UserStoppedSpeakingFrame',
    'LLMTokenFrame', 'LLMFullResponseFrame', 'TextSentenceFrame', 'WordTimestampFrame',
    'FunctionCallFrame', 'FunctionCallResultFrame',
    'InputImageFrame', 'UserImageFrame', 'OutputImageFrame', 'VisionTextFrame',
    'InputDTMFFrame', 'OutputDTMFFrame', 'MetricsFrame',
    'InterruptionFrame', 'CancelFrame', 'ErrorFrame', 'EndFrame', 'ControlFrame',
    'StartFrame', 'HeartbeatFrame', 'TTSStartedFrame', 'TTSStoppedFrame',
    'PauseFrame', 'ResumeFrame', 'TranscriptionUpdateFrame',
    'FrameProcessor', 'Pipeline', 'BaseObserver', 'Direction',
    'LLMContext', 'ToolRegistry',
    'WakeCheckFilter', 'FrameFilter', 'FunctionFilter', 'IdentityFilter', 'NullFilter',
    'STTMuteFilter', 'STTMuteStrategy', 'GatedProcessor',
    'PatternAggregator', 'DTMFAggregator', 'WordAggregator',
    'UserContextAggregator', 'AssistantContextAggregator',
    'InterruptionStrategy', 'AlwaysInterruptStrategy',
    'MinSpeechDurationStrategy', 'MinWordsInterruptionStrategy',
    'TranscriptProcessor', 'PipelineParams', 'WatchdogObserver',
    'AudioMixer', 'LongTermMemory', 'ProducerProcessor', 'ConsumerProcessor',
]
