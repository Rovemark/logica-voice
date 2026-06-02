/**
 * @logica-voice/adapter-whatsapp
 *
 * WhatsApp channel adapter via Baileys.
 *
 * CRÍTICO: preserva 3 fixes de segurança/qualidade do channels/whatsapp/bot.js do LogicaOS:
 *   1. LID resolution via msg.key.senderPn / participantPn (não confiar só em contacts store)
 *   2. BR phone normalize (9º dígito tolerante — 12d vs 13d)
 *   3. ACL fail-closed (allowlist vazia = DENY ALL, não open-world)
 *
 * Referência: /Users/andreambrosio/ambrosio-brain/channels/whatsapp/bot.js (linhas 340-450).
 */

import type {
  ChannelAdapter,
  ChannelMessage,
  SenderIdentity,
  SendOpts,
} from '@logica-voice/core';
import { BaseChannelAdapter, brPhoneVariants, isPhoneAllowed, detectMention } from '@logica-voice/core';
import * as BaileysNs from '@whiskeysockets/baileys';
const {
  makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
  Browsers,
} = BaileysNs as any;
type WASocket = ReturnType<typeof BaileysNs.makeWASocket>;
import pino from 'pino';

export interface WhatsAppAdapterConfig {
  /** Diretório pra salvar credenciais multi-device do Baileys */
  authDir: string;
  /** Lista de telefones permitidos (formato +5585991420169 ou 5585991420169) */
  allowedPhones?: string[];
  /** Lista de LIDs permitidos (formato 'NNNNNN@lid') — usar APENAS quando phone não resolve */
  allowedLids?: string[];
  /** Allow all (override explícito — NÃO recomendado prod) */
  allowAll?: boolean;
  /** Logger pra Baileys (default: silent pino) */
  logger?: pino.Logger;
}

export class WhatsAppAdapter extends BaseChannelAdapter implements ChannelAdapter {
  name = 'whatsapp';
  private sock?: WASocket;
  private reconnectAttempts = 0;
  private connectionState: 'closed' | 'connecting' | 'open' = 'closed';

  constructor(private config: WhatsAppAdapterConfig) {
    super();
    if (!config.authDir) throw new Error('WhatsAppAdapter: authDir obrigatório');
  }

  async start(): Promise<void> {
    if (this.started) return;
    await this._connect();
    this.started = true;
  }

  async stop(): Promise<void> {
    this.started = false;
    try {
      this.sock?.end(undefined);
    } catch {
      /* ignore */
    }
    this.connectionState = 'closed';
  }

  async isAlive(): Promise<boolean> {
    return this.connectionState === 'open' && !!this.sock?.user;
  }

  // ─── ACL fail-closed ──────────────────────────────────────────
  override isAllowed(sender: SenderIdentity): boolean {
    if (this.config.allowAll) return true;

    // Tenta resolver via phone
    if (sender.phone) {
      const phones = this.config.allowedPhones || [];
      if (isPhoneAllowed(sender.phone.replace(/\D/g, ''), phones)) return true;
    }

    // Fallback: LID explicitamente cadastrado
    if (sender.rawId?.endsWith('@lid')) {
      const lids = this.config.allowedLids || [];
      if (lids.includes(sender.rawId)) return true;
    }

    return false; // fail-closed
  }

  async sendText(chatId: string, text: string, _opts?: SendOpts): Promise<void> {
    if (!this.sock || this.connectionState !== 'open') {
      throw new Error('WhatsApp não conectado');
    }
    // Split em chunks de 4000 chars (limite suave do Baileys)
    for (let i = 0; i < text.length; i += 4000) {
      const chunk = text.slice(i, i + 4000);
      await this.sock.sendMessage(chatId, { text: chunk });
      if (i + 4000 < text.length) await this._sleep(300);
    }
  }

  async sendAudio(chatId: string, audio: Buffer | NodeJS.ReadableStream, _opts?: SendOpts): Promise<void> {
    if (!this.sock || this.connectionState !== 'open') throw new Error('WhatsApp não conectado');
    const buf = Buffer.isBuffer(audio) ? audio : await this._streamToBuffer(audio);
    await this.sock.sendMessage(chatId, {
      audio: buf,
      mimetype: 'audio/ogg; codecs=opus',
      ptt: true,
    });
  }

  async sendImage(chatId: string, image: Buffer | URL, caption?: string): Promise<void> {
    if (!this.sock || this.connectionState !== 'open') throw new Error('WhatsApp não conectado');
    if (image instanceof URL) {
      await this.sock.sendMessage(chatId, { image: { url: image.toString() }, caption });
    } else {
      await this.sock.sendMessage(chatId, { image, caption });
    }
  }

  async sendTyping(chatId: string, on: boolean): Promise<void> {
    if (!this.sock) return;
    try {
      await this.sock.sendPresenceUpdate(on ? 'composing' : 'paused', chatId);
    } catch {
      /* ignore */
    }
  }

  // ─── Connection lifecycle ─────────────────────────────────────

  private async _connect(): Promise<void> {
    const { state, saveCreds } = await useMultiFileAuthState(this.config.authDir);
    const { version } = await fetchLatestBaileysVersion();
    const logger = this.config.logger || pino({ level: 'silent' });

    this.connectionState = 'connecting';
    this.sock = makeWASocket({
      version,
      auth: state,
      browser: Browsers.ubuntu('Chrome'),
      printQRInTerminal: true,
      syncFullHistory: false,
      markOnlineOnConnect: false,
      logger: logger as any,
    });

    this.sock!.ev.on('creds.update', saveCreds);

    this.sock!.ev.on('connection.update', (update: any) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        console.log('[whatsapp] 📷 QR code disponível pra scan no terminal');
      }

      if (connection === 'open') {
        this.connectionState = 'open';
        this.reconnectAttempts = 0;
        console.log(`[whatsapp] ✓ conectado como ${this.sock?.user?.id}`);
      }

      if (connection === 'close') {
        this.connectionState = 'closed';
        const code = (lastDisconnect?.error as any)?.output?.statusCode;
        if (code === DisconnectReason.loggedOut) {
          console.error('[whatsapp] 🔴 LOGOUT (401). Apague authDir e reconecte.');
          process.exit(0); // PM2 não auto-restart se exit 0
        }
        // Reconnect com backoff
        if (this.started) {
          const delay = Math.min(5000 * Math.pow(1.5, this.reconnectAttempts), 60000);
          this.reconnectAttempts++;
          console.log(`[whatsapp] 🔄 reconectando em ${delay}ms (tentativa ${this.reconnectAttempts})`);
          setTimeout(() => this._connect().catch(console.error), delay);
        }
      }
    });

    this.sock!.ev.on('messages.upsert', async ({ messages, type }: any) => {
      if (type !== 'notify') return;
      for (const msg of messages) {
        if (!msg.message || msg.key.fromMe) continue;
        await this._handleMessage(msg);
      }
    });
  }

  private async _handleMessage(msg: any): Promise<void> {
    const remoteJid = msg.key.remoteJid as string;
    if (!remoteJid) return;

    const isGroup = remoteJid.endsWith('@g.us');
    const senderJid = isGroup ? (msg.key.participant as string) : remoteJid;

    // ✅ Resolve telefone real (LID fix)
    const phone = this._resolvePhone(senderJid, msg.key, isGroup);

    const text = this._extractText(msg);
    const mention = text ? detectMention(text) : null;

    const sender: SenderIdentity = {
      channel: 'whatsapp',
      rawId: senderJid,
      ...(phone ? { phone: '+' + phone } : {}),
      ...(msg.pushName ? { displayName: msg.pushName as string } : {}),
    };

    const channelMessage: ChannelMessage = {
      channel: 'whatsapp',
      chatId: remoteJid,
      sender,
      text: mention ? mention.cleanText : text,
      isGroup,
      ...(mention?.agent ? { mentionedAgent: mention.agent } : {}),
      raw: msg,
      receivedAt: new Date((msg.messageTimestamp as number) * 1000 || Date.now()),
    };

    // v0.2: extrair voice/image
    // const audio = msg.message?.audioMessage; — download via downloadMediaMessage

    await this._dispatch(channelMessage);
  }

  /**
   * Resolve número real do remetente.
   * - JID @s.whatsapp.net: extrai direto dos dígitos
   * - JID @lid (LID opaco do WhatsApp moderno): usa msg.key.senderPn (DM) ou participantPn (grupo)
   * - Fallback: contacts store (raramente populado)
   * - Retorna null se opaco mesmo (caller deve usar ACL via LID explicit)
   */
  private _resolvePhone(jidOrLid: string, key: any, isGroup: boolean): string | null {
    if (!jidOrLid) return null;
    if (jidOrLid.endsWith('@s.whatsapp.net')) {
      return jidOrLid.replace('@s.whatsapp.net', '').replace(/\D/g, '');
    }
    if (jidOrLid.endsWith('@lid')) {
      const pn = isGroup ? key?.participantPn : key?.senderPn;
      if (pn && typeof pn === 'string' && pn.includes('@s.whatsapp.net')) {
        return pn.replace('@s.whatsapp.net', '').replace(/\D/g, '');
      }
      const contact = ((this.sock as any)?.contacts)?.[jidOrLid];
      if (contact?.id && contact.id.includes('@s.whatsapp.net')) {
        return contact.id.replace('@s.whatsapp.net', '').replace(/\D/g, '');
      }
      return null;
    }
    return jidOrLid.replace(/@.*/, '').replace(/\D/g, '');
  }

  private _extractText(msg: any): string | undefined {
    const m = msg.message;
    if (!m) return undefined;
    return (
      m.conversation ||
      m.extendedTextMessage?.text ||
      m.imageMessage?.caption ||
      m.videoMessage?.caption ||
      undefined
    );
  }

  private async _streamToBuffer(stream: NodeJS.ReadableStream): Promise<Buffer> {
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(Buffer.from(chunk));
    return Buffer.concat(chunks);
  }

  private _sleep(ms: number): Promise<void> {
    return new Promise((r) => setTimeout(r, ms));
  }
}

// Re-export helpers úteis pra usuário
export { brPhoneVariants };
