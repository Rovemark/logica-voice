/**
 * Pipeline runner — compõe stages (VoiceService) que processam frames em streaming.
 * Cada stage consome frames do anterior e emite frames pro próximo.
 *
 * Inspirado em Pipecat: cada stage retorna AsyncIterable<Frame>, pull-based via for-await.
 */

import type { Frame, ControlFrame, InterruptionFrame, MetricsFrame } from './frames.js';
import { createFrame } from './frames.js';
import type { VoiceService } from './types.js';

export interface PipelineOptions {
  sessionId: string;
  /** AbortController pra cancelar a pipeline inteira */
  signal?: AbortSignal;
  /** Emite MetricsFrame após cada stage */
  emitMetrics?: boolean;
}

export class Pipeline {
  private stages: VoiceService[] = [];

  constructor(private opts: PipelineOptions) {}

  /** Adiciona um stage ao final da pipeline */
  addStage(service: VoiceService): this {
    this.stages.push(service);
    return this;
  }

  /** Inicializa todos os stages (lazy load de modelos) */
  async init(): Promise<void> {
    for (const stage of this.stages) {
      if (stage.init) await stage.init();
    }
  }

  /**
   * Roda a pipeline. Recebe stream de input frames, retorna stream de output frames.
   * Cada stage transforma o stream: stage1 → stage2 → ... → stageN.
   */
  async *run(input: AsyncIterable<Frame>): AsyncIterable<Frame> {
    let current: AsyncIterable<Frame> = input;
    for (const stage of this.stages) {
      const wrapped = this._wrapWithMetrics(stage, current);
      current = wrapped;
    }
    for await (const frame of current) {
      if (this.opts.signal?.aborted) {
        yield createFrame<ControlFrame>('control', this.opts.sessionId, {
          command: 'cancel',
        });
        return;
      }
      yield frame;
    }
  }

  /** Encerra todos os stages (cleanup) */
  async close(): Promise<void> {
    for (const stage of this.stages) {
      if (stage.close) await stage.close();
    }
  }

  /** Helper: wrap um stage pra emitir métricas por frame */
  private async *_wrapWithMetrics(
    stage: VoiceService,
    input: AsyncIterable<Frame>
  ): AsyncIterable<Frame> {
    const stageName = stage.name;
    for await (const outFrame of stage.process(input)) {
      yield outFrame;
      if (this.opts.emitMetrics) {
        yield createFrame<MetricsFrame>('metrics', this.opts.sessionId, {
          stage: stageName,
          durationMs: 0, // TODO: medir per-frame com performance.now()
        });
      }
    }
  }
}

// ─── Helpers pra propagação de InterruptionFrame ──────────────────

/**
 * Wrap um AsyncIterable pra reagir a InterruptionFrame:
 * quando recebe, chama cancel() e para de yieldar.
 */
export async function* withBargeIn(
  input: AsyncIterable<Frame>,
  onInterrupt: () => void | Promise<void>
): AsyncIterable<Frame> {
  for await (const frame of input) {
    if (frame.type === 'interruption') {
      await onInterrupt();
      yield frame;
      return;
    }
    yield frame;
  }
}

/**
 * Cria um stream vazio que termina imediatamente (útil pra testar pipeline).
 */
export async function* emptyStream(): AsyncIterable<Frame> {
  // empty
}
