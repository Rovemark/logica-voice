/**
 * Helpers base abstratos pra implementar ChannelAdapter/BrainAdapter/VoiceService.
 * Reduz boilerplate em cada implementação concreta.
 */

import type { ChannelAdapter, ChannelMessage, SenderIdentity } from './types.js';

// ═══════════════════════════════════════════════════════════════
// BASE CHANNEL ADAPTER
// ═══════════════════════════════════════════════════════════════

export abstract class BaseChannelAdapter implements ChannelAdapter {
  abstract name: string;
  protected handlers: Array<(msg: ChannelMessage) => Promise<void>> = [];
  protected started = false;

  abstract start(): Promise<void>;
  abstract stop(): Promise<void>;
  abstract isAlive(): Promise<boolean>;
  abstract sendText(chatId: string, text: string, opts?: import('./types.js').SendOpts): Promise<void>;
  abstract sendAudio(
    chatId: string,
    audio: Buffer | NodeJS.ReadableStream,
    opts?: import('./types.js').SendOpts
  ): Promise<void>;
  abstract sendImage(chatId: string, image: Buffer | URL, caption?: string): Promise<void>;
  abstract sendTyping(chatId: string, on: boolean): Promise<void>;

  onMessage(handler: (msg: ChannelMessage) => Promise<void>): void {
    this.handlers.push(handler);
  }

  isAllowed(_sender: SenderIdentity): boolean {
    // Default: allow tudo. Implementações concretas devem override com lógica de ACL.
    return true;
  }

  /** Dispatch interno — usado por implementações pra notificar handlers */
  protected async _dispatch(msg: ChannelMessage): Promise<void> {
    if (!this.isAllowed(msg.sender)) {
      console.log(`[${this.name}] 🚫 sender ${msg.sender.rawId} bloqueado`);
      return;
    }
    for (const h of this.handlers) {
      try {
        await h(msg);
      } catch (err) {
        console.error(`[${this.name}] handler erro:`, err);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// MENTION DETECTOR (compartilhado entre canais)
// ═══════════════════════════════════════════════════════════════

const MENTION_RE = /^@([a-z][a-z0-9_-]*)\s+/i;

/**
 * Detecta @mention no início da mensagem.
 * Retorna { agent, cleanText } se houver mention, senão null.
 */
export function detectMention(text: string): { agent: string; cleanText: string } | null {
  const m = text.match(MENTION_RE);
  if (!m) return null;
  return {
    agent: m[1]!.toLowerCase(),
    cleanText: text.slice(m[0].length).trim(),
  };
}

// ═══════════════════════════════════════════════════════════════
// BR PHONE NORMALIZER (pra WhatsApp principalmente)
// ═══════════════════════════════════════════════════════════════

/**
 * Gera variantes do número BR pra comparação tolerante (com ou sem 9º dígito).
 * Ex: '5585991420169' (13d) ↔ '558591420169' (12d) são equivalentes.
 */
export function brPhoneVariants(rawDigits: string): Set<string> {
  const out = new Set<string>();
  const d = String(rawDigits || '').replace(/\D/g, '');
  if (!d) return out;
  out.add(d);
  out.add('+' + d);
  // 55 + DDD (2d) + 8d = 12 total → adiciona 9º na posição 4
  if (d.startsWith('55') && d.length === 12) {
    const withNine = d.slice(0, 4) + '9' + d.slice(4);
    out.add(withNine);
    out.add('+' + withNine);
  } else if (d.startsWith('55') && d.length === 13 && d[4] === '9') {
    // Remove 9º
    const withoutNine = d.slice(0, 4) + d.slice(5);
    out.add(withoutNine);
    out.add('+' + withoutNine);
  }
  return out;
}

/**
 * Check tolerante: senderDigits está em allowedPhones (qualquer variante)?
 */
export function isPhoneAllowed(senderDigits: string, allowedPhones: string[]): boolean {
  if (!senderDigits || !allowedPhones?.length) return false;
  const senderVariants = brPhoneVariants(senderDigits);
  for (const p of allowedPhones) {
    const allowedVariants = brPhoneVariants(p.replace(/\D/g, ''));
    for (const v of senderVariants) {
      if (allowedVariants.has(v)) return true;
    }
  }
  return false;
}
