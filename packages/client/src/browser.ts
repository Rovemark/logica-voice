/**
 * browser.ts — Web Audio helpers: capture the mic into the client, play the bot's voice.
 *
 * Browser-only (uses getUserMedia + AudioContext). Pair with LogicaVoiceClient:
 *
 *   const vc = new LogicaVoiceClient('ws://127.0.0.1:8915');
 *   const player = createPlayer(vc);
 *   await vc.connect();
 *   const mic = await startMicrophone(vc);   // streams 16 kHz PCM to the pipeline
 *   // ... later: mic.stop(); player.stop();
 */

import { LogicaVoiceClient } from './client.js';
import { SAMPLE_RATE_IN, SAMPLE_RATE_OUT } from './protocol.js';

function floatToInt16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]!));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

/** Linear downsample Float32 from srcRate to dstRate (good enough for speech). */
function downsample(input: Float32Array, srcRate: number, dstRate: number): Float32Array {
  if (dstRate >= srcRate) return input;
  const ratio = srcRate / dstRate;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) out[i] = input[Math.floor(i * ratio)]!;
  return out;
}

export interface MicHandle { stop: () => void; }

/**
 * Capture the microphone and stream 16 kHz PCM into the client.
 * Returns a handle with stop(). Requires a secure context (https/localhost).
 */
export async function startMicrophone(
  client: LogicaVoiceClient,
  opts: { sampleRate?: number; echoCancellation?: boolean } = {},
): Promise<MicHandle> {
  const target = opts.sampleRate ?? SAMPLE_RATE_IN;
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: opts.echoCancellation ?? true, noiseSuppression: true, channelCount: 1 },
  });
  const AC: typeof AudioContext = (window as any).AudioContext || (window as any).webkitAudioContext;
  const ctx = new AC();
  const source = ctx.createMediaStreamSource(stream);
  // ScriptProcessor is deprecated but universally available; fine for a reference SDK.
  const node = ctx.createScriptProcessor(4096, 1, 1);
  node.onaudioprocess = (e: AudioProcessingEvent) => {
    const input = e.inputBuffer.getChannelData(0);
    const down = downsample(input, ctx.sampleRate, target);
    client.sendAudio(floatToInt16(down));
  };
  source.connect(node);
  node.connect(ctx.destination);
  return {
    stop: () => {
      try { node.disconnect(); source.disconnect(); } catch { /* noop */ }
      stream.getTracks().forEach(t => t.stop());
      void ctx.close();
    },
  };
}

export interface PlayerHandle {
  /** Stop playback and clear the queue (e.g. on barge-in). */
  stop: () => void;
}

/**
 * Play the bot's voice. Subscribes to the client's `audio` events (PCM 24 kHz int16)
 * and schedules them gaplessly. Clears its queue on `interrupted` for instant barge-in.
 */
export function createPlayer(
  client: LogicaVoiceClient,
  opts: { sampleRate?: number } = {},
): PlayerHandle {
  const rate = opts.sampleRate ?? SAMPLE_RATE_OUT;
  const AC: typeof AudioContext = (window as any).AudioContext || (window as any).webkitAudioContext;
  const ctx = new AC();
  let cursor = 0;          // next start time
  const sources = new Set<AudioBufferSourceNode>();

  const enqueue = (pcm: ArrayBuffer) => {
    const i16 = new Int16Array(pcm);
    if (i16.length === 0) return;
    const buf = ctx.createBuffer(1, i16.length, rate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < i16.length; i++) ch[i] = i16[i]! / 0x8000;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const now = ctx.currentTime;
    const startAt = Math.max(now, cursor);
    src.start(startAt);
    cursor = startAt + buf.duration;
    sources.add(src);
    src.onended = () => sources.delete(src);
  };

  const clear = () => {
    for (const s of sources) { try { s.stop(); } catch { /* already stopped */ } }
    sources.clear();
    cursor = 0;
  };

  client.on('audio', enqueue);
  client.on('interrupted', clear);

  return {
    stop: () => { client.off('audio', enqueue); client.off('interrupted', clear); clear(); void ctx.close(); },
  };
}
