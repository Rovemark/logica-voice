"""
frames.py — Tipos de frame que fluem pelo pipeline LVP.

Frames são pacotes imutáveis (dataclasses) que passam de processor em processor.
Dois sentidos:
  - DOWNSTREAM (mic → speaker): áudio entra, vira texto, vira resposta, vira áudio
  - UPSTREAM (speaker → mic): controle, interrupção (barge-in tem prioridade)

System frames (InterruptionFrame, EndFrame) são tratados na hora, fora da fila normal.
"""

from dataclasses import dataclass, field
import time


@dataclass
class Frame:
    """Base. Todo frame carrega timestamp de criação pra medir latência."""
    ts: float = field(default_factory=time.time, kw_only=True)


# ─── Áudio ───────────────────────────────────────────────────────────

@dataclass
class AudioInFrame(Frame):
    """PCM int16 mono vindo do mic (16kHz). Bytes crus."""
    pcm: bytes = b''
    sample_rate: int = 16000


@dataclass
class AudioOutFrame(Frame):
    """PCM int16 mono pra tocar no speaker (24kHz)."""
    pcm: bytes = b''
    sample_rate: int = 24000
    text: str = ''  # texto que originou esse áudio (debug)


# ─── VAD / turn detection ────────────────────────────────────────────

@dataclass
class UserStartedSpeakingFrame(Frame):
    """VAD detectou início de fala."""
    pass


@dataclass
class UserStoppedSpeakingFrame(Frame):
    """VAD detectou fim de fala (silêncio > threshold). Carrega o áudio acumulado."""
    audio_wav: bytes = b''
    duration_ms: int = 0


# ─── STT ─────────────────────────────────────────────────────────────

@dataclass
class InterimTranscriptionFrame(Frame):
    """Transcrição PARCIAL (enquanto user ainda fala). Pode mudar."""
    text: str = ''


@dataclass
class TranscriptionFrame(Frame):
    """Transcrição FINAL (após fim da fala)."""
    text: str = ''


# ─── LLM ─────────────────────────────────────────────────────────────

@dataclass
class LLMTokenFrame(Frame):
    """Um token (ou pedaço) gerado pelo LLM em streaming."""
    text: str = ''


@dataclass
class LLMFullResponseFrame(Frame):
    """Resposta completa do LLM (fim do turno)."""
    text: str = ''


@dataclass
class TextSentenceFrame(Frame):
    """Uma sentença completa pronta pra TTS (saída do SentenceAggregator)."""
    text: str = ''


# ─── Controle / sistema (prioridade alta) ────────────────────────────

@dataclass
class ControlFrame(Frame):
    """Frame de controle genérico (config, comandos)."""
    action: str = ''
    data: dict = field(default_factory=dict)


@dataclass
class InterruptionFrame(Frame):
    """Barge-in: user falou em cima do Astro. Cancela TUDO downstream imediatamente."""
    pass


@dataclass
class ErrorFrame(Frame):
    """Erro em algum processor."""
    message: str = ''
    source: str = ''


@dataclass
class EndFrame(Frame):
    """Fim da sessão. Cada processor faz cleanup."""
    pass
