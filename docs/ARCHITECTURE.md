# ARCHITECTURE — Logica Voice

## Princípio

> **Canais são burros. Brain é inteligente. Adapter é a cola.**

Cada canal (WhatsApp, Telegram, Voice) é um adapter que:
1. Recebe input (texto, áudio, imagem)
2. Normaliza pra `ChannelMessage` (formato unificado)
3. Manda pro brain (`synapses/chat-loop.js`)
4. Recebe `AgentResponse` streaming
5. Renderiza no formato do canal (Markdown, áudio, vídeo)

Brain orchestra os agentes. Adapter cuida só do transport.

---

## Diagrama mental

```
┌──────────────────────────────────────────────────────────────────┐
│                          USUÁRIO                                 │
└──┬────────────┬────────────┬────────────┬──────────────────────┘
   │            │            │            │
   ▼            ▼            ▼            ▼
┌──────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
│ WApp │  │Telegram │  │L. Voice │  │ Web Chat│   ← CANAIS
└──┬───┘  └────┬────┘  └────┬────┘  └────┬────┘
   │           │            │            │
   └───────────┴────────────┴────────────┘
                       │
                       ▼
        ┌─────────────────────────────────┐
        │      ADAPTERS (Logica Conv)     │
        │  ┌──────────────────────────┐   │
        │  │ ChannelMessage (unif.)   │   │
        │  │ AgentResponse (unif.)    │   │
        │  └──────────────────────────┘   │
        └────────────────┬────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────┐
        │  AUDIO LAYER (Pipecat / Moshi)  │
        │  ┌──────────────────────────┐   │
        │  │ STT → text               │   │  ← voice only
        │  │ text → TTS               │   │
        │  │ VAD + barge-in           │   │
        │  └──────────────────────────┘   │
        └────────────────┬────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────┐
        │  BRAIN (LogicaOS Synapses)      │
        │  ├─ chat-loop.js                │
        │  ├─ orchestrator.js (chains)    │
        │  ├─ llm-router.js (Qwen/Claude) │
        │  ├─ memory-hub.js (recall)      │
        │  └─ 130+ agents + 50+ clones    │
        └─────────────────────────────────┘
```

---

## Componente 1: Adapter (camada de canal)

### Interface comum

Toda implementação de canal (WhatsApp, Telegram, Voice, Web) implementa:

```ts
interface ChannelAdapter {
  name: 'whatsapp' | 'telegram' | 'voice' | 'web';

  // Lifecycle
  start(): Promise<void>;
  stop(): Promise<void>;
  isAlive(): Promise<boolean>;

  // Listeners
  onMessage(handler: (msg: ChannelMessage) => Promise<void>): void;

  // Senders
  sendText(chatId: string, text: string, opts?: SendOpts): Promise<void>;
  sendAudio(chatId: string, audio: Buffer | Stream, opts?: SendOpts): Promise<void>;
  sendImage(chatId: string, image: Buffer | URL, caption?: string): Promise<void>;
  sendTyping(chatId: string, on: boolean): Promise<void>;

  // ACL
  isAllowed(senderIdentity: SenderIdentity): boolean;
}

interface ChannelMessage {
  channel: string;             // 'whatsapp' | 'telegram' | ...
  chatId: string;              // identifier do chat/conversa
  sender: SenderIdentity;      // quem mandou (resolvido)
  text?: string;
  audio?: AudioPayload;        // {buffer, mimeType, duration}
  image?: ImagePayload;
  isGroup: boolean;
  mentionedAgent?: string;     // @luna na msg → 'luna'
  raw: unknown;                // payload original do canal
  receivedAt: Date;
}

interface SenderIdentity {
  channel: string;
  rawId: string;              // ex: '5585991420169@s.whatsapp.net'
  phone?: string;             // normalizado BR (com/sem 9º dígito)
  username?: string;
  displayName?: string;
}

interface AgentResponse {
  text?: string;
  audio?: AudioStream;        // se voice canal
  attachments?: Attachment[];
  agentSlug?: string;
  health?: number;
  thinking?: string;          // opcional pra mostrar reasoning
}
```

### Adapters concretos

```
adapters/
├── base.ts                    # interface ChannelAdapter
├── whatsapp/
│   ├── index.ts              # implementa ChannelAdapter via Baileys
│   ├── lid-resolver.ts       # fix do bug LID (já resolvido no LogicaOS)
│   └── br-phone-normalizer.ts
├── telegram/
│   ├── index.ts              # via Telegraf
│   └── voice-handler.ts      # voz nativa Telegram → STT pipeline
├── voice/
│   ├── index.ts              # via Pipecat WebSocket
│   ├── pipecat-pipeline.py   # pipeline Python embedded
│   └── moshi-bridge.py       # modo Jarvis (opcional)
└── web/
    └── index.ts              # via WebSocket pro dashboard React
```

---

## Componente 2: Audio Layer

### Modo Padrão (qualidade Telegram/WhatsApp/Voice push-to-talk)

Pipeline sequencial via **Pipecat**:

```
[áudio user] 
   ↓
[VAD detecta fim de fala] 
   ↓
[STT — faster-whisper MLX] 
   ↓
[texto vai pro brain via chat-loop.js]
   ↓
[brain retorna stream de tokens]
   ↓
[TTS — Kokoro ou F5-TTS, streaming]
   ↓
[áudio sai chunk-by-chunk pro user]
```

**Latência alvo:** 800ms-1.5s round-trip.

### Modo Jarvis (Logica Voice contínuo)

Bypass do pipeline com **Kyutai Moshi**:

```
[mic stream contínuo] 
   ↓
[Moshi full-duplex (escuta + fala simultâneo)]
   ↓
[output audio stream contínuo]
```

**Latência alvo:** 160-200ms (igual Gemini Live).

**Tradeoff:** menos contexto do brain (Moshi tem sua própria inteligência speech-only), mas conversa naturalíssima. Usado pra interações rápidas; pra trabalho profundo o user toggla pro Modo Padrão.

### Switcher

Comando `/voz contínua on|off` no canal alterna entre os modos.

---

## Componente 3: Brain Bridge

Logica Voice **NÃO duplica** lógica de IA. Reusa o brain LogicaOS:

```ts
// bridge.ts
import { chatWithTools } from '../../../synapses/chat-loop';

export async function processMessage(msg: ChannelMessage): Promise<AgentResponse> {
  const targetAgent = msg.mentionedAgent || resolveAgentFromContext(msg);

  const stream = await chatWithTools({
    agent: targetAgent,
    task: msg.text || await sttTranscribe(msg.audio),
    channel: msg.channel,
    chatId: msg.chatId,
    workspace: msg.sender.rawId,
    onChunk: (chunk) => emitToAdapter(msg.channel, msg.chatId, chunk),
  });

  return formatResponse(stream);
}
```

### Routing de agente
- **Default:** CEO configurado (ex: Aurora)
- **Mention:** `@luna`, `@dev`, `@story` → roteia direto
- **Chain trigger:** `/chain lançamento` → invoca chain multi-agent
- **Auto:** brain decide via classifier (existente em `llm-router.js`)

### Memory persistente
- Toda conversa salva em `chat_messages` (Supabase já tem schema)
- Recall via `memory-hub.recall(agent, taskText)` (já implementado)
- Cross-channel: mensagem no Telegram lembra de conversa do WhatsApp (mesma identidade resolvida)

---

## Componente 4: Identidade Unificada

Problema: usuário fala no WhatsApp (`+5585991420169@s.whatsapp.net`), Telegram (`@andreambrosio`, ID 732596559), Logica Voice (sem ID estável). Brain precisa saber é a MESMA pessoa.

### Solução: Identity Registry

```
contacts (já existe no LogicaOS)
├── id (uuid)
├── canonical_name        # "Andre Ambrosio"
├── identities[]          # ['whatsapp:5585991420169', 'telegram:732596559', 'voice:host:macbook-pro']
├── tags                  # ['owner', 'architect']
└── metadata              # JSON livre (avatar URL, prefs, etc)
```

Cada adapter tem um `identity-resolver.ts` que mapeia raw ID → contact UUID. Memory engine sempre usa o UUID (não o raw ID) pra recall.

---

## Componente 5: ACL & Anti-flood

### ACL (allow-list)
- Por canal: `WHATSAPP_ALLOWED`, `TELEGRAM_CHAT_ID`, `VOICE_ALLOWED_HOSTS`
- Unificado em `config/acl.yaml`:
  ```yaml
  channels:
    whatsapp:
      allow_phones: ["+5585991420169"]
      allow_lids:   ["28596160745525@lid"]
    telegram:
      allow_user_ids: [732596559]
    voice:
      allow_hostnames: ["macbook-pro-de-andre.local"]
  ```

### Dedup (anti-flood)
- Notifier dedup já implementado em `synapses/notifier.js` (commit recente).
- Janela default 6h normal, 1h `priority='high'`.
- Cada adapter chama `notifier.notifyArchitect(subject, body, opts)` → dedup automático.

---

## Componente 6: Observability

- **Logs:** structured-logger (existente) → JSONL
- **Métricas:** `synapses/metrics-collector.js` (counters, gauges, p50/p95)
- **Audit:** action-trail.jsonl (já existe)
- **Cache hit/miss:** logado por chat-loop (já mostra read/creation tokens)

---

## Componente 7: Distribuição

### CLI (`logica-voice`)
```bash
npx logica-voice init my-bot
cd my-bot
logica setup       # wizard interativo
logica start       # roda tudo (PM2)
logica stop
logica status
logica logs <channel>
```

### Docker compose (cliente avançado)
```yaml
services:
  brain:        # synapses-api
  pipecat:      # voice orchestration (Python)
  pgvector:     # memory
  logica-conv:  # bridge + adapters
```

### Instalação minima (single binary futuro)
- `npx logica-voice` baixa releases pré-buildados
- MLX models baixam on-demand
- Setup termina em <5min

---

## Roadmap técnico

| Fase | Entrega | Componentes |
|---|---|---|
| **0** | Adapter base + Brain bridge | `adapters/base.ts`, `bridge.ts` |
| **1** | WhatsApp + Telegram (refator) | Mover `channels/*` pra cá |
| **2** | Voice Pipecat | `adapters/voice/`, pipeline Python |
| **3** | Modo Jarvis (Moshi) | `adapters/voice/moshi-bridge.py` |
| **4** | CLI + Docker + docs | `bin/logica`, `docker-compose.yml` |
| **5** | Open source release | Tag v0.1, anúncio público |

---

## Decisões abertas (preciso resolver)

1. **Pipecat embedded ou microserviço?** Embedded simplifica deploy mas força Python na stack. Microsvc isola mas precisa orquestração.
2. **MLX dependência hard ou opcional?** Hard = facilita Mac, exclui Linux. Opcional = mais complexo.
3. **Wake word local?** Picovoice Porcupine (free pra dev, custo de licença em produção). Alternative: Snowboy (descontinuado), modelo customizado.
4. **Voice cloning UX?** Setup wizard pede 10s de áudio → gera embedding F5-TTS. Onde armazenar? Local-only ou Supabase?

Próximo passo: criar `docs/DECISIONS.md` (ADRs) pra travar essas.
