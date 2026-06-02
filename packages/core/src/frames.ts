/**
 * Frame types — discriminated unions que fluem pelo pipeline.
 * Inspirado em Pipecat (Daily.co, BSD-2). Reimplementado em TypeScript pra Logica Voice.
 */

export type FrameType =
  | 'audio_in'
  | 'audio_out'
  | 'transcript'
  | 'llm_messages'
  | 'llm_response'
  | 'text'
  | 'start'
  | 'end'
  | 'error'
  | 'interruption'
  | 'metrics'
  | 'control';

export interface FrameBase {
  /** ID único pra dedup/tracking */
  id: string;
  /** Timestamp epoch ms */
  timestamp: number;
  /** Identificador da sessão (mantém estado entre frames) */
  sessionId: string;
  /** Metadata livre (custom por stage) */
  metadata?: Record<string, unknown>;
}

/** Audio capturado do mic (entrada) */
export interface AudioRawFrame extends FrameBase {
  type: 'audio_in';
  /** PCM data (geralmente Int16 little-endian) */
  data: Buffer | Uint8Array;
  sampleRate: number;
  channels: number;
  /** ms de áudio que esse chunk representa */
  durationMs?: number;
}

/** Audio sintetizado pra output (TTS → speaker) */
export interface AudioOutFrame extends FrameBase {
  type: 'audio_out';
  data: Buffer | Uint8Array;
  sampleRate: number;
  channels: number;
  /** Última chunk dessa síntese? */
  isFinal?: boolean;
}

/** Resultado do STT */
export interface TranscriptionFrame extends FrameBase {
  type: 'transcript';
  text: string;
  isFinal: boolean;
  /** Idioma detectado/usado */
  language?: string;
  /** Confiança 0-1 */
  confidence?: number;
}

/** Messages enviadas ao LLM */
export interface LLMMessagesFrame extends FrameBase {
  type: 'llm_messages';
  messages: Array<{ role: 'system' | 'user' | 'assistant' | 'tool'; content: string; name?: string }>;
  /** Slug do agente que deve responder */
  agent?: string;
}

/** Chunk de resposta do LLM (streaming) */
export interface LLMResponseFrame extends FrameBase {
  type: 'llm_response';
  delta: string;
  /** Acumulado até agora (opcional, alguns stages preferem) */
  cumulative?: string;
  isFinal: boolean;
  /** Tokens consumidos (final apenas) */
  usage?: { inputTokens: number; outputTokens: number; cacheReadTokens?: number; cacheCreateTokens?: number };
}

/** Texto puro pra TTS ou display */
export interface TextFrame extends FrameBase {
  type: 'text';
  text: string;
  /** Slug do agente cujo texto é esse (pra escolher voz) */
  agent?: string;
}

/** Início de sessão/pipeline */
export interface StartFrame extends FrameBase {
  type: 'start';
}

/** Fim de sessão/pipeline */
export interface EndFrame extends FrameBase {
  type: 'end';
  reason?: string;
}

/** Erro propagado pelo pipeline */
export interface ErrorFrame extends FrameBase {
  type: 'error';
  error: string;
  /** Stage que originou */
  stage?: string;
  recoverable?: boolean;
}

/** Interruption (barge-in) — propagar pra cancelar TTS atual */
export interface InterruptionFrame extends FrameBase {
  type: 'interruption';
  /** Stage que detectou (geralmente VAD) */
  source: string;
}

/** Métricas de stage (latência, tokens, custo) */
export interface MetricsFrame extends FrameBase {
  type: 'metrics';
  stage: string;
  durationMs: number;
  /** Métricas livres */
  data?: Record<string, number | string>;
}

/** Comandos de controle (cancel, pause, resume, switch_mode) */
export interface ControlFrame extends FrameBase {
  type: 'control';
  command: 'cancel' | 'pause' | 'resume' | 'switch_mode' | 'flush';
  args?: Record<string, unknown>;
}

/** Union type de todos os frames */
export type Frame =
  | AudioRawFrame
  | AudioOutFrame
  | TranscriptionFrame
  | LLMMessagesFrame
  | LLMResponseFrame
  | TextFrame
  | StartFrame
  | EndFrame
  | ErrorFrame
  | InterruptionFrame
  | MetricsFrame
  | ControlFrame;

// ─── Helpers ──────────────────────────────────────────────────────

let _counter = 0;
function nextId(): string {
  return `frm_${Date.now().toString(36)}_${(_counter++).toString(36)}`;
}

export function createFrame<T extends Frame>(
  type: T['type'],
  sessionId: string,
  data: Omit<T, keyof FrameBase | 'type'>
): T {
  return {
    id: nextId(),
    timestamp: Date.now(),
    sessionId,
    type,
    ...data,
  } as T;
}

export function isAudioFrame(f: Frame): f is AudioRawFrame | AudioOutFrame {
  return f.type === 'audio_in' || f.type === 'audio_out';
}

export function isTextLike(f: Frame): f is TranscriptionFrame | LLMResponseFrame | TextFrame {
  return f.type === 'transcript' || f.type === 'llm_response' || f.type === 'text';
}
