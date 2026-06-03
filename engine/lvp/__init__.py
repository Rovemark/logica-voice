"""
LVP — Logica Voice Pipeline
============================

Arquitetura de pipeline de voz por frames, 100% nossa (inspirada em Pipecat mas
sem nenhuma dependência dele). Frames fluem por uma cadeia de FrameProcessors,
cada um transformando/reagindo. Permite streaming real e barge-in (interrupção).

Fluxo canônico:
  TransportInput → VAD → STT → ContextUser → LLM → SentenceAggregator → TTS → TransportOutput

Diferença pro modo blocking antigo: cada estágio começa assim que o anterior
emite o primeiro frame — não espera o anterior terminar. É o que derruba a latência.
"""

from .frames import (
    Frame,
    AudioInFrame,
    AudioOutFrame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    LLMTokenFrame,
    LLMFullResponseFrame,
    TextSentenceFrame,
    InterruptionFrame,
    ErrorFrame,
    EndFrame,
    ControlFrame,
)
from .processor import FrameProcessor, Pipeline

__all__ = [
    'Frame', 'AudioInFrame', 'AudioOutFrame', 'TranscriptionFrame',
    'InterimTranscriptionFrame', 'UserStartedSpeakingFrame', 'UserStoppedSpeakingFrame',
    'LLMTokenFrame', 'LLMFullResponseFrame', 'TextSentenceFrame', 'InterruptionFrame',
    'ErrorFrame', 'EndFrame', 'ControlFrame', 'FrameProcessor', 'Pipeline',
]
