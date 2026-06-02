/**
 * @logica-voice/cli — Logica Voice command-line interface
 *
 * Comandos:
 *   logica-voice init [name]      Cria projeto novo
 *   logica-voice setup            Wizard interativo
 *   logica-voice start            Inicia adapters + brain + voice pipeline
 *   logica-voice stop             Encerra graceful
 *   logica-voice status           Mostra estado dos canais
 *   logica-voice logs <channel>   Streamifica logs de um canal
 *   logica-voice voice <cmd>      Sub-comandos de voz (list, test, record, import-clone)
 *   logica-voice version          Mostra versão
 */

import { Command } from 'commander';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml';

import type { ChannelAdapter, BrainAdapter, ChannelMessage } from '@logica-voice/core';
import { detectMention } from '@logica-voice/core';

const VERSION = '0.1.0';

// ─── Helpers ─────────────────────────────────────────────────────

function defaultConfigYaml(projectName: string): string {
  return `# Logica Voice config
name: ${projectName}

channels:
  telegram:
    enabled: false
    token: \${TELEGRAM_BOT_TOKEN}
    allowedChatIds: []
  whatsapp:
    enabled: false
    authDir: ./.wa-auth
    allowedPhones: []

brain:
  provider: built-in   # ou 'logicaos', 'openai-compatible'
  defaultLlm:
    provider: openai
    model: gpt-4o
    apiKey: \${OPENAI_API_KEY}
  defaultAgent: assistant
  agents:
    - slug: assistant
      name: Assistant
      systemPrompt: "Você é um assistente útil em PT-BR. Seja direto e prestativo."

voice:
  stt: faster-whisper   # ou 'cloud'
  tts: kokoro            # ou 'f5-tts', 'elevenlabs'
  mode: standard         # ou 'jarvis' (Moshi full-duplex)
`;
}

function loadConfig(cwd = process.cwd()): any {
  const path = join(cwd, 'logica-voice.yaml');
  if (!existsSync(path)) {
    throw new Error(`Config não encontrada: ${path}. Rode \`logica-voice init\` primeiro.`);
  }
  const raw = readFileSync(path, 'utf-8');
  const interpolated = raw.replace(/\$\{([A-Z0-9_]+)\}/g, (_m, name) => process.env[name] || '');
  return parseYaml(interpolated);
}

// ─── Command handlers ───────────────────────────────────────────

async function cmdInit(name: string | undefined): Promise<void> {
  const projectName = name || 'my-logica-voice';
  const dir = join(process.cwd(), projectName);
  if (existsSync(dir)) {
    console.error(`Diretório ${dir} já existe.`);
    process.exit(1);
  }
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'logica-voice.yaml'), defaultConfigYaml(projectName));
  writeFileSync(
    join(dir, '.env.example'),
    `OPENAI_API_KEY=\nTELEGRAM_BOT_TOKEN=\nWHATSAPP_ALLOWED=\n`
  );
  writeFileSync(join(dir, '.gitignore'), `.env\n.wa-auth/\nnode_modules/\n`);
  console.log(`✓ Projeto criado em ${dir}`);
  console.log(`  Próximo: cd ${projectName} && cp .env.example .env && edite .env`);
  console.log(`  Depois: logica-voice start`);
}

async function cmdSetup(): Promise<void> {
  console.log('Wizard interativo em v0.2. Por enquanto edite logica-voice.yaml manualmente.');
}

async function cmdStart(): Promise<void> {
  const cfg = loadConfig();
  console.log(`[logica-voice] iniciando "${cfg.name}"...`);

  // Brain
  const brain = await loadBrain(cfg);
  console.log(`[brain] ${brain.name} pronto (alive=${await brain.isAlive()})`);

  // Canais
  const adapters: ChannelAdapter[] = [];
  if (cfg.channels?.telegram?.enabled) {
    const { TelegramAdapter } = await import('@logica-voice/adapter-telegram');
    const tg = new TelegramAdapter(cfg.channels.telegram);
    adapters.push(tg);
  }
  if (cfg.channels?.whatsapp?.enabled) {
    const { WhatsAppAdapter } = await import('@logica-voice/adapter-whatsapp');
    const wa = new WhatsAppAdapter(cfg.channels.whatsapp);
    adapters.push(wa);
  }

  if (adapters.length === 0) {
    console.warn('[logica-voice] ⚠ Nenhum canal habilitado em logica-voice.yaml');
  }

  for (const adapter of adapters) {
    adapter.onMessage(async (msg: ChannelMessage) => {
      await handleMessage(adapter, brain, msg);
    });
    await adapter.start();
    console.log(`[${adapter.name}] ✓ ativo`);
  }

  // Graceful shutdown
  process.on('SIGINT', async () => {
    console.log('\n[logica-voice] encerrando...');
    for (const a of adapters) await a.stop().catch(() => {});
    process.exit(0);
  });

  // Keep alive
  await new Promise(() => {});
}

async function loadBrain(cfg: any): Promise<BrainAdapter> {
  const provider = cfg.brain?.provider;
  if (!provider) throw new Error('brain.provider não configurado em logica-voice.yaml');

  if (provider === 'built-in') {
    const { BuiltInBrain } = await import('@logica-voice/brain-built-in');
    return new BuiltInBrain(cfg.brain);
  }
  if (provider === 'logicaos') {
    const { LogicaOSBrain } = await import('@logica-voice/brain-logicaos');
    return new LogicaOSBrain(cfg.brain);
  }
  throw new Error(`Brain provider desconhecido: ${provider}`);
}

async function handleMessage(adapter: ChannelAdapter, brain: BrainAdapter, msg: ChannelMessage): Promise<void> {
  if (!msg.text) return; // v0.1: só texto

  // Typing indicator
  await adapter.sendTyping(msg.chatId, true).catch(() => {});

  let response = '';
  try {
    for await (const chunk of brain.chat({
      message: msg.text,
      ...(msg.mentionedAgent ? { agent: msg.mentionedAgent } : {}),
      channel: msg.channel,
      chatId: msg.chatId,
      sender: msg.sender,
    })) {
      if (chunk.type === 'text' && chunk.content) {
        response += chunk.content;
      } else if (chunk.type === 'error') {
        response = `[erro: ${chunk.content || 'unknown'}]`;
        break;
      }
    }
  } catch (err) {
    response = `[erro: ${(err as Error).message}]`;
  }

  if (response) {
    await adapter.sendText(msg.chatId, response);
  }
}

async function cmdStatus(): Promise<void> {
  console.log(`logica-voice v${VERSION}`);
  console.log('Status detalhado em v0.2');
}

async function cmdLogs(_channel: string): Promise<void> {
  console.log('Comando logs em v0.2');
}

async function cmdVoiceList(): Promise<void> {
  console.log('Voice list em v0.2');
}

// ─── Main ───────────────────────────────────────────────────────

export async function main(argv: string[]): Promise<void> {
  const program = new Command();
  program.name('logica-voice').description('Logica Voice CLI').version(VERSION);

  program
    .command('init [name]')
    .description('Cria novo projeto Logica Voice')
    .action(cmdInit);

  program.command('setup').description('Wizard interativo (v0.2)').action(cmdSetup);

  program.command('start').description('Inicia adapters + brain').action(cmdStart);

  program.command('stop').description('Encerra graceful').action(() => {
    console.log('Use Ctrl+C ou kill no PID/PM2.');
  });

  program.command('status').description('Mostra status').action(cmdStatus);

  program
    .command('logs <channel>')
    .description('Streamifica logs')
    .action(cmdLogs);

  const voice = program.command('voice').description('Sub-comandos de voz');
  voice.command('list').description('Lista vozes').action(cmdVoiceList);

  await program.parseAsync(argv);
}
