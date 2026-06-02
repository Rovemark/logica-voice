/**
 * Interfaces principais do Logica Voice.
 * Channel adapters, brain adapters, voice services — todos seguem contratos aqui.
 */

import type { Frame } from './frames.js';

// ═══════════════════════════════════════════════════════════════
// CHANNEL ADAPTER (WhatsApp, Telegram, Voice desktop, Web, etc)
// ═══════════════════════════════════════════════════════════════

export interface SenderIdentity {
  channel: string;
  /** ID bruto do canal (ex: '5585991420169@s.whatsapp.net', '732596559', 'lid:28596160745525@lid') */
  rawId: string;
  /** Telefone normalizado (BR aceita 12 ou 13 dígitos) */
  phone?: string;
  username?: string;
  displayName?: string;
}

export interface ChannelMessage {
  channel: string;
  chatId: string;
  sender: SenderIdentity;
  text?: string;
  audio?: AudioPayload;
  image?: ImagePayload;
  isGroup: boolean;
  /** @mention detectada no início da msg → slug do agente */
  mentionedAgent?: string;
  /** Payload original do canal (debug) */
  raw: unknown;
  receivedAt: Date;
}

export interface AudioPayload {
  data: Buffer;
  mimeType: string;
  durationMs?: number;
}

export interface ImagePayload {
  data: Buffer | URL;
  mimeType?: string;
  caption?: string;
}

export interface SendOpts {
  replyTo?: string;
  silent?: boolean;
}

export interface ChannelAdapter {
  name: string;

  /** Inicia listening (polling/webhook/WebSocket) */
  start(): Promise<void>;
  /** Encerra graceful */
  stop(): Promise<void>;
  /** Checa se conectado */
  isAlive(): Promise<boolean>;

  /** Registra handler pra mensagens novas */
  onMessage(handler: (msg: ChannelMessage) => Promise<void>): void;

  /** Envia texto pro chat */
  sendText(chatId: string, text: string, opts?: SendOpts): Promise<void>;
  /** Envia áudio (voice note ou file) */
  sendAudio(chatId: string, audio: Buffer | NodeJS.ReadableStream, opts?: SendOpts): Promise<void>;
  /** Envia imagem com legenda opcional */
  sendImage(chatId: string, image: Buffer | URL, caption?: string): Promise<void>;
  /** Indica "digitando..." (typing) */
  sendTyping(chatId: string, on: boolean): Promise<void>;

  /** Allowlist check (ACL fail-closed) */
  isAllowed(sender: SenderIdentity): boolean;
}

// ═══════════════════════════════════════════════════════════════
// BRAIN ADAPTER (OpenAI, Claude, Gemini, Ollama, MLX, LogicaOS, custom)
// ═══════════════════════════════════════════════════════════════

export interface BrainInput {
  message: string;
  /** Slug do agente alvo (override de mention/default) */
  agent?: string;
  /** Histórico recente da conversa */
  history?: HistoryMessage[];
  channel: string;
  chatId: string;
  sender: SenderIdentity;
  /** Metadata livre (system prompt override, tools custom, etc) */
  metadata?: Record<string, unknown>;
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
  agent?: string;
  timestamp?: number;
}

export type BrainChunkType = 'text' | 'tool_call' | 'tool_result' | 'thinking' | 'done' | 'error';

export interface BrainChunk {
  type: BrainChunkType;
  /** Texto incremental (delta) ou content final */
  content?: string;
  /** Tool call info (quando type='tool_call') */
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  /** Metadata final (tokens, model, latency, etc) */
  metadata?: Record<string, unknown>;
}

export interface AgentDef {
  slug: string;
  name: string;
  role?: string;
  systemPrompt?: string;
  tools?: string[];
  voice?: string;
  /** Override de LLM por agente */
  llm?: { provider: string; model: string };
}

export interface BrainAdapter {
  name: string;

  /** Stream de resposta do brain — async iterable de chunks */
  chat(input: BrainInput): AsyncIterable<BrainChunk>;

  /** Lista agentes disponíveis (opcional — pra discovery) */
  listAgents?(): Promise<AgentDef[]>;

  /** Health check */
  isAlive(): Promise<boolean>;
}

// ═══════════════════════════════════════════════════════════════
// VOICE SERVICE (STT, TTS, full-duplex)
// ═══════════════════════════════════════════════════════════════

export interface VoiceService {
  name: string;
  /** Inicializa modelo (lazy load) */
  init?(): Promise<void>;
  /** Processa stream de frames in → stream de frames out */
  process(input: AsyncIterable<Frame>): AsyncIterable<Frame>;
  /** Cleanup (kill subprocess, close WS, unload model) */
  close?(): Promise<void>;
}

// ═══════════════════════════════════════════════════════════════
// AGENT RESPONSE (resultado consolidado pra entregar no canal)
// ═══════════════════════════════════════════════════════════════

export interface AgentResponse {
  text?: string;
  audio?: AsyncIterable<AudioPayload>;
  attachments?: Array<{ type: string; url?: string; data?: Buffer }>;
  agentSlug?: string;
  /** Saúde da resposta 0-100 (quality score) */
  health?: number;
  /** Texto de "pensamento" (chain-of-thought, opcional pra UI) */
  thinking?: string;
  /** Tokens consumidos */
  tokensIn?: number;
  tokensOut?: number;
  /** Latência total ms */
  durationMs?: number;
}
