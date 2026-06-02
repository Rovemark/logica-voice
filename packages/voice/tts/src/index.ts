/**
 * @logica-voice/voice-tts
 *
 * Text-to-speech via Kokoro-82M (default rápido) ou F5-TTS (voice clone).
 *
 * v0.1: stub. v0.2: implementação completa via subprocess Python ou kokoro-js.
 *
 * Pool de vozes Kokoro pra auto-assign por gender/personality (Tier 1).
 */

import type { Frame, TextFrame, AudioOutFrame, VoiceService } from '@logica-voice/core';
import { createFrame } from '@logica-voice/core';

export interface KokoroConfig {
  /** Voice ID (ver KOKORO_VOICES) — default 'af_sky' */
  voice?: string;
  /** Velocidade (0.5-2.0) — default 1.0 */
  speed?: number;
  /** Sample rate output (default 24000) */
  sampleRate?: number;
  /** Path do modelo (auto-download se omitido) */
  modelPath?: string;
}

export const KOKORO_VOICES = {
  female: {
    sky: 'af_sky',
    bella: 'af_bella',
    sarah: 'af_sarah',
    nicole: 'af_nicole',
  },
  male: {
    michael: 'am_michael',
    liam: 'am_liam',
    will: 'am_will',
    george: 'am_george',
    fenrir: 'am_fenrir',
  },
} as const;

/**
 * Auto-assign de voice baseado em gender + personality (Tier 1).
 */
export function autoAssignKokoroVoice(opts: { gender?: 'male' | 'female'; personality?: string }): string {
  const personality = (opts.personality || '').toLowerCase();
  if (opts.gender === 'female') {
    if (/energ|criativ|copy/.test(personality)) return KOKORO_VOICES.female.bella;
    if (/calm|professional|profissional/.test(personality)) return KOKORO_VOICES.female.sarah;
    if (/técnic|preciso/.test(personality)) return KOKORO_VOICES.female.nicole;
    return KOKORO_VOICES.female.sky;
  }
  if (opts.gender === 'male') {
    if (/assertiv|vendas/.test(personality)) return KOKORO_VOICES.male.will;
    if (/expressiv|criativ/.test(personality)) return KOKORO_VOICES.male.liam;
    if (/dramatic|grave/.test(personality)) return KOKORO_VOICES.male.fenrir;
    if (/técnic|engenh/.test(personality)) return KOKORO_VOICES.male.michael;
    return KOKORO_VOICES.male.george;
  }
  return KOKORO_VOICES.female.sky;
}

export class KokoroTTS implements VoiceService {
  name = 'kokoro';

  constructor(_config: KokoroConfig = {}) {
    // TODO v0.2: carrega modelo via kokoro-js OU ONNX runtime OU subprocess Python
  }

  async init(): Promise<void> {
    // TODO v0.2
  }

  async *process(input: AsyncIterable<Frame>): AsyncIterable<Frame> {
    // TODO v0.2: pra cada TextFrame, sintetiza chunks AudioOutFrame
    for await (const frame of input) {
      yield frame; // passthrough placeholder
    }
  }

  /** Helper standalone — sintetiza texto inteiro pra buffer */
  async synthesize(_text: string): Promise<Buffer> {
    throw new Error('KokoroTTS.synthesize: implementação completa em v0.2');
  }

  async close(): Promise<void> {
    /* nothing yet */
  }
}

// Tipos pra conveniência
export type { TextFrame, AudioOutFrame };
