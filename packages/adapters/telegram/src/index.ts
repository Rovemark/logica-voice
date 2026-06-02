/**
 * @logica-voice/adapter-telegram
 *
 * Telegram Bot API adapter (long polling). Implementação inicial pra texto;
 * áudio/imagem chegam em v0.2.
 *
 * Inspirado em channels/telegram/bot.js do LogicaOS (mantém patterns testados:
 * offset persistente, polling backoff, 409 conflict handling).
 */

import type {
  ChannelAdapter,
  ChannelMessage,
  SenderIdentity,
  SendOpts,
} from '@logica-voice/core';
import { BaseChannelAdapter, detectMention } from '@logica-voice/core';

export interface TelegramAdapterConfig {
  /** Bot token de @BotFather */
  token: string;
  /** Allowlist de chat_ids (string). Vazio = allow all (NÃO recomendado prod) */
  allowedChatIds?: string[];
  /** Allow all? Override explícito (default: false se allowedChatIds vazio) */
  allowAll?: boolean;
  /** Polling timeout em segundos (default 25) */
  pollingTimeout?: number;
  /** API base URL (override pra testes) */
  apiBaseUrl?: string;
}

const DEFAULT_API = 'https://api.telegram.org';

export class TelegramAdapter extends BaseChannelAdapter implements ChannelAdapter {
  name = 'telegram';
  private offset = 0;
  private pollingActive = false;
  private pollAbort?: AbortController;
  private backoffMs = 3000;

  constructor(private config: TelegramAdapterConfig) {
    super();
    if (!config.token) throw new Error('TelegramAdapter: token obrigatório');
  }

  async start(): Promise<void> {
    if (this.started) return;
    // Verifica token via getMe
    const me = await this._call('getMe', {});
    if (!me.ok) throw new Error(`Telegram getMe falhou: ${JSON.stringify(me)}`);
    this.started = true;
    this.pollingActive = true;
    this._pollLoop().catch((err) => {
      console.error('[telegram] poll loop crashed:', err);
    });
  }

  async stop(): Promise<void> {
    this.pollingActive = false;
    this.pollAbort?.abort();
    this.started = false;
  }

  async isAlive(): Promise<boolean> {
    try {
      const r = await this._call('getMe', {});
      return Boolean(r.ok);
    } catch {
      return false;
    }
  }

  override isAllowed(sender: SenderIdentity): boolean {
    if (this.config.allowAll) return true;
    if (!this.config.allowedChatIds?.length) return false; // fail-closed
    return this.config.allowedChatIds.includes(sender.rawId);
  }

  async sendText(chatId: string, text: string, opts?: SendOpts): Promise<void> {
    // Split em chunks de 4000 chars (limite Telegram = 4096)
    for (let i = 0; i < text.length; i += 4000) {
      const chunk = text.slice(i, i + 4000);
      await this._call('sendMessage', {
        chat_id: chatId,
        text: chunk,
        parse_mode: 'Markdown',
        disable_web_page_preview: true,
        ...(opts?.replyTo ? { reply_to_message_id: Number(opts.replyTo) } : {}),
        ...(opts?.silent ? { disable_notification: true } : {}),
      });
    }
  }

  async sendAudio(chatId: string, audio: Buffer | NodeJS.ReadableStream, opts?: SendOpts): Promise<void> {
    // v0.2: multipart upload OGG/Opus pra sendVoice
    // Por enquanto, fallback pra mensagem indicando que áudio ainda não está implementado
    const form = new FormData();
    form.append('chat_id', chatId);
    const blob = audio instanceof Buffer ? new Blob([new Uint8Array(audio)]) : new Blob([]);
    form.append('voice', blob, 'voice.ogg');
    if (opts?.replyTo) form.append('reply_to_message_id', String(opts.replyTo));
    await this._callForm('sendVoice', form);
  }

  async sendImage(chatId: string, image: Buffer | URL, caption?: string): Promise<void> {
    if (image instanceof URL) {
      await this._call('sendPhoto', { chat_id: chatId, photo: image.toString(), caption });
      return;
    }
    const form = new FormData();
    form.append('chat_id', chatId);
    form.append('photo', new Blob([new Uint8Array(image)]), 'image.jpg');
    if (caption) form.append('caption', caption);
    await this._callForm('sendPhoto', form);
  }

  async sendTyping(chatId: string, on: boolean): Promise<void> {
    if (!on) return; // Telegram limpa typing após 5s automaticamente
    await this._call('sendChatAction', { chat_id: chatId, action: 'typing' });
  }

  // ─── Internos ──────────────────────────────────────────────────

  private async _pollLoop(): Promise<void> {
    while (this.pollingActive) {
      this.pollAbort = new AbortController();
      try {
        const res = await this._call(
          'getUpdates',
          {
            offset: this.offset,
            timeout: this.config.pollingTimeout ?? 25,
            allowed_updates: ['message', 'edited_message', 'callback_query'],
          },
          { signal: this.pollAbort.signal }
        );
        if (res.ok && Array.isArray(res.result)) {
          for (const update of res.result) {
            this.offset = Math.max(this.offset, update.update_id + 1);
            await this._handleUpdate(update);
          }
          this.backoffMs = 3000; // reset backoff
        } else if (res.error_code === 409) {
          console.warn('[telegram] 409 conflict — outro processo polling. Backoff 30s.');
          await this._sleep(30000);
        }
      } catch (err) {
        if (!this.pollingActive) break;
        console.error('[telegram] poll error:', (err as Error).message);
        await this._sleep(this.backoffMs);
        this.backoffMs = Math.min(this.backoffMs * 1.5, 60000);
      }
    }
  }

  private async _handleUpdate(update: any): Promise<void> {
    const msg = update.message || update.edited_message;
    if (!msg) return;

    const chatId = String(msg.chat.id);
    const fromId = String(msg.from?.id || '');
    const text = msg.text || msg.caption || '';
    const mention = detectMention(text);

    const sender: SenderIdentity = {
      channel: 'telegram',
      rawId: fromId,
      username: msg.from?.username,
      displayName: [msg.from?.first_name, msg.from?.last_name].filter(Boolean).join(' '),
    };

    const channelMessage: ChannelMessage = {
      channel: 'telegram',
      chatId,
      sender,
      text: mention ? mention.cleanText : text,
      isGroup: msg.chat.type === 'group' || msg.chat.type === 'supergroup',
      mentionedAgent: mention?.agent,
      raw: update,
      receivedAt: new Date(msg.date * 1000),
    };

    // v0.2: extrair voice/photo se presente
    // if (msg.voice) channelMessage.audio = await this._downloadFile(msg.voice.file_id);
    // if (msg.photo) channelMessage.image = await this._downloadFile(msg.photo[msg.photo.length-1].file_id);

    await this._dispatch(channelMessage);
  }

  private async _call(
    method: string,
    params: Record<string, unknown>,
    opts: { signal?: AbortSignal } = {}
  ): Promise<any> {
    const base = this.config.apiBaseUrl || DEFAULT_API;
    const url = `${base}/bot${this.config.token}/${method}`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
      signal: opts.signal,
    });
    return res.json();
  }

  private async _callForm(method: string, form: FormData): Promise<any> {
    const base = this.config.apiBaseUrl || DEFAULT_API;
    const url = `${base}/bot${this.config.token}/${method}`;
    const res = await fetch(url, { method: 'POST', body: form });
    return res.json();
  }

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
