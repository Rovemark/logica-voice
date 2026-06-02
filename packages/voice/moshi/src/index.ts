/**
 * @logica-voice/voice-moshi
 *
 * Full-duplex speech-to-speech via Kyutai Moshi (MLX em Apple Silicon).
 * Modo "Jarvis" — latência ~200ms, conversação contínua tipo Gemini Live.
 *
 * v0.1: stub. v0.2: implementação via WebSocket bridge pra moshi_mlx Python.
 *
 * Usuário precisa rodar 1x:
 *   pip install moshi_mlx
 */

import type { Frame, AudioRawFrame, AudioOutFrame, VoiceService } from '@logica-voice/core';

export interface MoshiConfig {
  /** Endpoint do servidor Moshi WebSocket (default ws://localhost:8998) */
  endpoint?: string;
  /** Auto-spawn servidor moshi_mlx? (default true) */
  autoStartServer?: boolean;
  /** Python interpreter path (default 'python3') */
  pythonPath?: string;
}

export class MoshiFullDuplex implements VoiceService {
  name = 'moshi-mlx';

  constructor(_config: MoshiConfig = {}) {
    // TODO v0.2
  }

  async init(): Promise<void> {
    // TODO v0.2: spawn moshi_mlx server + connect WS
    throw new Error('MoshiFullDuplex: implementação completa em v0.2 (precisa Python bridge)');
  }

  async *process(input: AsyncIterable<Frame>): AsyncIterable<Frame> {
    // TODO v0.2: pra cada AudioRawFrame, envia binary pro Moshi WS
    // recebe AudioOutFrame chunks (Moshi gera fala em paralelo à escuta)
    for await (const frame of input) {
      yield frame; // placeholder
    }
  }

  async close(): Promise<void> {
    /* nothing yet */
  }
}

export type { AudioRawFrame, AudioOutFrame };
