# Pipecat Comparison — o que herdamos, o que reimaginamos

> **Crédito:** Logica Voice é fortemente inspirado em [Pipecat](https://github.com/pipecat-ai/pipecat) (Daily.co, BSD-2). Sem Pipecat, não existiria essa visão arquitetural. Este doc é transparência sobre o que viemos e o que mudamos.

---

## O que mantemos do Pipecat (filosofia)

### 1. Frame-based streaming pipeline
Pipecat processa áudio em **frames** (chunks) que fluem pelo pipeline. Cada estágio (VAD → STT → LLM → TTS) recebe frames, processa, emite novos frames.

**Logica Conv adota.** Frames são a abstração central:
```ts
interface Frame {
  type: 'audio_in' | 'audio_out' | 'transcript' | 'llm_text' | 'meta' | 'control';
  data?: Buffer | string;
  timestamp: number;
  sessionId: string;
}
```

### 2. Vendor-neutral adapters
No Pipecat, trocar TTS = mudar 1 linha (`ElevenLabsTTSService` → `CartesiaTTSService`).

**Logica Conv adota** — adapters pra TTS, STT, LLM, transport, brain.

### 3. SmartTurnDetection (LLM-based)
Pipecat v1.0 (abr/26) usa um classificador LLM pra detectar fim de turno (vs VAD puro). Reduz interruptions em 30%.

**Logica Conv implementa próprio** — Qwen3-4B local classifica "user terminou?" em <300ms.

### 4. Barge-in nativo
User interrompe → bot para de falar imediatamente. Pipecat tem isso embedded.

**Logica Conv adota.** VAD monitora durante TTS output; se detecta speech, cancela playback.

### 5. Observability via metrics
Cada estágio reporta latência, tokens, custo.

**Logica Conv adota.** Métricas Prometheus-compatible + dashboard built-in.

---

## O que mudamos (justificadamente)

### 1. TypeScript no lugar de Python ❗
**Razão técnica:**
- Logica Conv inclui canais (Baileys/WhatsApp, Telegraf/Telegram) que são bibliotecas JS nativas.
- Brain LogicaOS é Node — bundling sem subprocess fica natural.
- Front-end (dashboard React) compartilha tipos via TS.

**Tradeoff:**
- Perde acesso direto a torch/transformers (Python tem mais modelos).
- **Mitigation:** STT/TTS rodam como subprocess Python (faster-whisper, F5-TTS) com binding limpo, ou via WebSocket (Moshi).
- Core do orchestrator (frames, pipeline) é TS puro.

### 2. Canais (WA/TG) como first-class citizens ❗❗
**No Pipecat:** canais são "transports" simples (WebSocket, Daily, LiveKit). WhatsApp/Telegram não existem out-of-box — você liga manual.

**No Logica Conv:** canais reais (WA, TG, Voice, Web) são adapters próprios mantidos no core. Setup wizard pergunta quais ativar, configura tudo (token, QR, etc).

**Razão:** público-alvo do Logica Conv é "construir agentes que falam em canais reais", não "construir pipeline de áudio genérico". Pipecat é ferramenta de pipeline; Logica Conv é produto end-to-end.

### 3. Multi-agent built-in ❗❗❗
**No Pipecat:** 1 LLM por pipeline. Multi-agent precisa montar fora.

**No Logica Conv:**
- `agents.yaml` define múltiplos agentes
- Mention `@cleo` ou `@dev` roteia automaticamente
- Brain adapter "logicaos" expõe 130+ agentes prontos
- Chains multi-agent suportadas via `/chain xxx`

**Razão:** maioria dos casos reais (suporte, vendas, assistente) precisa de multi-agente. Pipecat força você reinventar.

### 4. Brain adapters expansíveis
**No Pipecat:** LLM services (`OpenAILLMService`, `AnthropicLLMService`) são parte do core.

**No Logica Conv:** brain é um **adapter no nível mais alto** — não está no pipeline de áudio. Permite:
- Brain custom HTTP (qualquer linguagem)
- LogicaOS integration (HTTP /api/chat/stream)
- Built-in agents (sem brain externo)
- Multi-brain (cada agente seu próprio brain)

**Razão:** desacopla pipeline de áudio da inteligência. Permite usar mesmo pipeline com brain different.

### 5. Local-first defaults
**No Pipecat:** ElevenLabs / OpenAI / Cartesia (cloud) são defaults nos tutoriais.

**No Logica Conv:** Kokoro / faster-whisper / Ollama (local) são defaults. ElevenLabs vira **opt-in** explícito.

**Razão:** filosofia "100% free, 100% local por padrão". Cliente decide ativar cloud se quiser.

### 6. Bundling com LogicaOS
**No Pipecat:** standalone, você integra manual em qualquer projeto.

**No Logica Conv:** standalone TAMBÉM, mas com **opção de bundling** com LogicaOS no setup. Quando bundled:
- Compartilha `.env`
- Reusa Supabase (pgvector)
- Brain adapter "logicaos" pré-configurado
- 130+ agentes auto-disponíveis

### 7. Modo Jarvis (Moshi) integrado
**No Pipecat:** Moshi não está embedded; você teria que escrever pipeline custom.

**No Logica Conv:** modo Jarvis é toggle nativo. STT+LLM+TTS clássico OU Moshi full-duplex.

---

## Tabela completa de diferenças

| Aspecto | Pipecat | Logica Voice |
|---|---|---|
| Linguagem core | Python | TypeScript (Node) |
| Licença | BSD-2 | MIT |
| Empresa | Daily.co (comercial) | Rovemark (Andre Ambrosio, indie) |
| Versão | v1.0 (abr/26) | v0.1 (em design jun/26) |
| WhatsApp | ❌ DIY | ✅ Baileys built-in |
| Telegram | ❌ DIY | ✅ Telegraf built-in |
| Voz desktop | ⚠️ via WebSocket DIY | ✅ pipeline próprio + cliente Mac/Win |
| Multi-agent | ❌ | ✅ `agents.yaml` + mentions |
| Modo Jarvis (full-duplex) | ❌ | ✅ Moshi MLX |
| Voice cloning local | ⚠️ via plug | ✅ F5-TTS embedded |
| ElevenLabs | ✅ default sugerido | ✅ opt-in |
| Local 100% | ⚠️ possível mas DIY | ✅ default |
| Brain adapters | LLM services | Brain abstraction (HTTP-first) |
| Frame model | ✅ | ✅ herdado |
| SmartTurn | ✅ v1.0 | ✅ Qwen3-4B local |
| Barge-in | ✅ | ✅ |
| Observability | ✅ | ✅ |
| Setup wizard | ❌ DIY | ✅ CLI interativo |
| Docker | ✅ exemplos | ✅ compose pronto |
| Bundling com brain stack | ❌ | ✅ LogicaOS first-class |

---

## Quando usar cada um

### Use **Pipecat** se:
- Stack é Python (Django, FastAPI)
- Quer máxima customização do pipeline de áudio
- Comunidade Python grande pra suporte
- Já tem brain próprio e só precisa orquestração de áudio
- Não precisa de canais (WA/TG) — só voz

### Use **Logica Voice** se:
- Quer canais (WA/TG/Voice) prontos sem ter que codar
- Stack é Node/TypeScript (ou tanto faz)
- Quer multi-agent fácil
- Quer voice cloning local sem pagar ElevenLabs
- Quer integrar com LogicaOS (130+ agentes prontos)
- Prefere wizard interativo a configurar YAML manual

### Use **ambos**?
- Sim, se você precisa de feature MUITO específica do Pipecat que ainda não migramos.
- Adapter "pipecat" virá em v0.3 — permite usar pipeline Pipecat dentro do Logica Conv.

---

## Reconhecimento da comunidade

- **Daily.co + Pipecat team**: arquitetura referência do espaço.
- **Kyutai Labs**: Moshi mudou o que é possível em latência <200ms.
- **OpenAI Whisper team**: STT open source de qualidade.
- **Resemble (Chatterbox), F5-TTS authors**: democratizaram voice cloning.
- **Baileys (WhiskeySockets)**: WhatsApp acessível sem cloud paga.

Logica Voice não compete com Pipecat — **complementa**. Cada um pra seu nicho.

---

## Pode migrar de Pipecat pra Logica Conv?

Sim, especialmente se:
- Quer adicionar WhatsApp/Telegram sem extra code
- Quer ir 100% local (não depender de ElevenLabs/OpenAI)
- Quer multi-agent sem reescrever orquestração

Migration guide chega em v0.4.

## Pode migrar de Logica Conv pra Pipecat?

Sim, especialmente se:
- Precisa de feature avançada do Pipecat não disponível ainda
- Equipe é toda Python e prefere ecossistema nativo
- Quer integrar com Daily.co infra (WebRTC managed)

Em ambos casos: as decisões arquiteturais (frames, adapters, streaming) são compatíveis o suficiente pra migração não ser reescrita do zero.
