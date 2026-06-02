/**
 * @logica-voice/voice-stt
 *
 * Speech-to-text via faster-whisper (subprocess Python WebSocket).
 *
 * Como funciona:
 *   1. `init()` spawn um servidor Python (`scripts/whisper_server.py`) que carrega o modelo.
 *   2. Conecta WebSocket no servidor.
 *   3. `process()` recebe AsyncIterable<AudioRawFrame>, envia chunks via WS, recebe TranscriptionFrame.
 *
 * Usuário precisa rodar 1x:
 *   pip install faster-whisper websockets
 *
 * (Ou usar mlx-whisper em Apple Silicon — auto-detect no script.)
 */

import type { Frame, AudioRawFrame, TranscriptionFrame, VoiceService } from '@logica-voice/core';
import { createFrame } from '@logica-voice/core';

export interface FasterWhisperConfig {
  /** Model size: 'tiny' | 'base' | 'small' | 'medium' | 'large-v3' (default) */
  model?: string;
  /** 'auto' | 'cpu' | 'cuda' | 'mps' | 'mlx' (default 'auto') */
  device?: string;
  /** Idioma (default 'auto') */
  language?: string;
  /** Porta do servidor Python (default 8901) */
  port?: number;
  /** Auto-spawn servidor Python? (default true) */
  autoStartServer?: boolean;
  /** Path pra python interpreter (default 'python3') */
  pythonPath?: string;
}

export class FasterWhisperSTT implements VoiceService {
  name = 'faster-whisper';
  private ws?: any; // WebSocket — lazy import
  // private serverProc?: ChildProcess; // lazy import

  constructor(_config: FasterWhisperConfig = {}) {
    // TODO v0.2: implementar spawn + WS
  }

  async init(): Promise<void> {
    // TODO v0.2:
    // if (config.autoStartServer) spawn python scripts/whisper_server.py
    // connect ws://localhost:{port}
    // wait "ready" handshake
    throw new Error('FasterWhisperSTT: implementação completa em v0.2 (precisa Python bridge)');
  }

  async *process(input: AsyncIterable<Frame>): AsyncIterable<Frame> {
    // TODO v0.2:
    // pra cada AudioRawFrame, envia binary frame pro WS
    // recebe transcription event → yield TranscriptionFrame
    for await (const _frame of input) {
      // placeholder: passa frames sem modificar
      yield _frame;
    }
  }

  async close(): Promise<void> {
    this.ws?.close?.();
  }
}

// Tipos auxiliares re-exported pra conveniência
export type { AudioRawFrame, TranscriptionFrame };
