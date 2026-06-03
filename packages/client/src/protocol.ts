/**
 * protocol.ts — the Logica Voice live wire protocol (client side).
 *
 * The pipeline speaks a tiny protocol over one WebSocket:
 *   client → server : binary PCM 16 kHz int16 mono (mic), or a JSON control message
 *   server → client : binary PCM 24 kHz int16 mono (bot voice), or a JSON event
 *
 * These are the JSON events the server emits (see the engine's transport). Binary
 * messages in either direction are raw PCM — no header.
 */

export interface ReadyEvent {
  type: 'ready';
  sample_rate_in: number;
  sample_rate_out: number;
  engine: string;
}

export interface SttPartialEvent { type: 'stt_partial'; text: string; }
export interface SttFinalEvent { type: 'stt_final'; text: string; }
export interface LlmTokenEvent { type: 'llm_token'; text: string; }
export interface LlmDoneEvent { type: 'llm_done'; text: string; }
/** Precedes a binary PCM chunk of the bot's voice. */
export interface TtsChunkEvent { type: 'tts_chunk'; size: number; text?: string; }
export interface VadEvent { type: 'vad'; speaking: boolean; }
export interface InterruptedEvent { type: 'interrupted'; }
export interface MetricsEvent { type: 'metrics'; metrics: Record<string, number>; }
export interface ErrorEvent { type: 'error'; message: string; }

export type ServerEvent =
  | ReadyEvent | SttPartialEvent | SttFinalEvent | LlmTokenEvent | LlmDoneEvent
  | TtsChunkEvent | VadEvent | InterruptedEvent | MetricsEvent | ErrorEvent;

/** Control messages the client can send to the server. */
export type ControlAction = 'interrupt' | 'end';
export interface ControlMessage { type: 'control'; action: ControlAction; }

/** Default sample rates of the protocol. */
export const SAMPLE_RATE_IN = 16000;   // mic → server
export const SAMPLE_RATE_OUT = 24000;  // server → speaker

/** Parse a text frame into a typed ServerEvent (or null if it isn't valid JSON). */
export function parseServerEvent(data: string): ServerEvent | null {
  try {
    const obj = JSON.parse(data);
    return obj && typeof obj.type === 'string' ? (obj as ServerEvent) : null;
  } catch {
    return null;
  }
}
