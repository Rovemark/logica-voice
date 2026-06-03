/**
 * client.ts — LogicaVoiceClient: one WebSocket, typed events.
 *
 * Works in the browser (global WebSocket) and Node (pass `ws`). You feed it mic PCM and
 * listen for transcripts, tokens, and the bot's voice audio. Barge-in is one call.
 *
 *   const vc = new LogicaVoiceClient('ws://127.0.0.1:8915');
 *   vc.on('sttFinal', t => console.log('you said', t));
 *   vc.on('audio', pcm => player.play(pcm));   // bot voice, PCM 24k int16
 *   await vc.connect();
 *   vc.sendAudio(micPcm16k);                    // Int16Array / ArrayBuffer
 *   vc.interrupt();                             // talk over the bot
 */

import {
  parseServerEvent, type ServerEvent, type ReadyEvent, type ControlAction,
} from './protocol.js';

export interface VoiceClientEvents {
  open: () => void;
  ready: (e: ReadyEvent) => void;
  sttPartial: (text: string) => void;
  sttFinal: (text: string) => void;
  token: (text: string) => void;
  response: (text: string) => void;
  audio: (pcm: ArrayBuffer) => void;     // bot voice, PCM 24 kHz int16 mono
  vad: (speaking: boolean) => void;
  interrupted: () => void;
  metrics: (metrics: Record<string, number>) => void;
  error: (err: Error) => void;
  close: () => void;
}

type WSImpl = {
  new (url: string): {
    binaryType: string;
    send(data: ArrayBufferLike | string | Uint8Array): void;
    close(): void;
    addEventListener?: (t: string, cb: (ev: any) => void) => void;
    onopen?: ((ev: any) => void) | null;
    onmessage?: ((ev: any) => void) | null;
    onerror?: ((ev: any) => void) | null;
    onclose?: ((ev: any) => void) | null;
  };
};

export interface VoiceClientOptions {
  /** WebSocket implementation. Browser: omit (uses global). Node: pass `ws`. */
  WebSocketImpl?: WSImpl;
}

export class LogicaVoiceClient {
  readonly url: string;
  private _ws: InstanceType<WSImpl> | null = null;
  private readonly _WS: WSImpl;
  private readonly _handlers = new Map<keyof VoiceClientEvents, Set<Function>>();

  constructor(url: string, opts: VoiceClientOptions = {}) {
    this.url = url;
    const WS = opts.WebSocketImpl ?? (globalThis as any).WebSocket;
    if (!WS) throw new Error('No WebSocket available — pass opts.WebSocketImpl (e.g. `ws` in Node).');
    this._WS = WS as WSImpl;
  }

  // ─── typed event emitter ───────────────────────────────────────────
  on<K extends keyof VoiceClientEvents>(event: K, cb: VoiceClientEvents[K]): this {
    if (!this._handlers.has(event)) this._handlers.set(event, new Set());
    this._handlers.get(event)!.add(cb);
    return this;
  }
  off<K extends keyof VoiceClientEvents>(event: K, cb: VoiceClientEvents[K]): this {
    this._handlers.get(event)?.delete(cb);
    return this;
  }
  private _emit<K extends keyof VoiceClientEvents>(event: K, ...args: Parameters<VoiceClientEvents[K]>): void {
    const hs = this._handlers.get(event);
    if (!hs) return;
    for (const h of hs) { try { (h as (...a: unknown[]) => void)(...args); } catch { /* listener threw */ } }
  }

  // ─── lifecycle ─────────────────────────────────────────────────────
  /** Open the connection. Resolves with the server's `ready` event. */
  connect(): Promise<ReadyEvent> {
    return new Promise((resolve, reject) => {
      const ws = new this._WS(this.url);
      ws.binaryType = 'arraybuffer';
      this._ws = ws;
      let opened = false;

      const onOpen = () => { opened = true; this._emit('open'); };
      const onMessage = (ev: { data: unknown }) => {
        const data = ev.data;
        if (typeof data === 'string') {
          const evt = parseServerEvent(data);
          if (evt) { this._route(evt); if (evt.type === 'ready') resolve(evt); }
        } else {
          this._toArrayBuffer(data).then(buf => { if (buf) this._emit('audio', buf); });
        }
      };
      const onError = () => { const e = new Error('WebSocket error'); this._emit('error', e); if (!opened) reject(e); };
      const onClose = () => this._emit('close');

      if (ws.addEventListener) {
        ws.addEventListener('open', onOpen);
        ws.addEventListener('message', onMessage);
        ws.addEventListener('error', onError);
        ws.addEventListener('close', onClose);
      } else {
        ws.onopen = onOpen; ws.onmessage = onMessage; ws.onerror = onError; ws.onclose = onClose;
      }
    });
  }

  /** Send a chunk of microphone audio (PCM 16 kHz int16 mono). */
  sendAudio(pcm: Int16Array | ArrayBuffer | Uint8Array): void {
    if (!this._ws) throw new Error('not connected');
    const buf = pcm instanceof Int16Array
      ? new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength)
      : pcm instanceof Uint8Array ? pcm : new Uint8Array(pcm);
    this._ws.send(buf);
  }

  /** Barge-in: tell the pipeline to stop speaking immediately. */
  interrupt(): void { this._control('interrupt'); }
  /** End the session cleanly. */
  end(): void { this._control('end'); }
  /** Close the socket. */
  close(): void { try { this._ws?.close(); } catch { /* already closing */ } this._ws = null; }

  private _control(action: ControlAction): void {
    this._ws?.send(JSON.stringify({ type: 'control', action }));
  }

  private _route(evt: ServerEvent): void {
    switch (evt.type) {
      case 'ready': this._emit('ready', evt); break;
      case 'stt_partial': this._emit('sttPartial', evt.text); break;
      case 'stt_final': this._emit('sttFinal', evt.text); break;
      case 'llm_token': this._emit('token', evt.text); break;
      case 'llm_done': this._emit('response', evt.text); break;
      case 'vad': this._emit('vad', evt.speaking); break;
      case 'interrupted': this._emit('interrupted'); break;
      case 'metrics': this._emit('metrics', evt.metrics); break;
      case 'error': this._emit('error', new Error(evt.message)); break;
      case 'tts_chunk': /* metadata; the binary PCM follows as the next message */ break;
    }
  }

  private async _toArrayBuffer(data: unknown): Promise<ArrayBuffer | null> {
    if (data instanceof ArrayBuffer) return data;
    // Browser Blob
    if (typeof Blob !== 'undefined' && data instanceof Blob) return await data.arrayBuffer();
    // Node Buffer / Uint8Array
    const u8 = data as Uint8Array;
    if (u8 && typeof u8.byteLength === 'number' && u8.buffer) {
      return u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength) as ArrayBuffer;
    }
    return null;
  }
}
