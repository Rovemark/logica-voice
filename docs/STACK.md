# STACK — componentes 2026

Cada escolha é justificada com benchmarks e fontes públicas. Toda comparação foi feita em jun/2026.

---

## 1. Orquestração de voz: **Pipecat** (BSD-2)

### Por que
- **v1.0 em abril/2026** — production-ready.
- **60+ adaptadores out-of-box**: trocar TTS/STT/LLM = mudar 1 linha.
- **SmartTurnDetection** (LLM-based) reduz "agent fala em cima do user" em ~30% vs VAD puro.
- Pipeline streaming nativo: TTS começa antes do LLM terminar → latência -60%.
- Roda em **localhost** com zero infra extra (vs LiveKit que exige Docker).

### Alternativa considerada: **LiveKit Agents** (Apache 2.0)
- Mais forte se a base for WebRTC cloud-first (LiveKit é o backbone).
- Modelo "room" nativo pra multi-participante.
- **Rejeitado** pra Logica Voice porque queremos rodar local-first; WebRTC vira opcional, não obrigação.

### Veredito
- **Logica Voice (desktop):** Pipecat na máquina do usuário (Python embedded ou via brain).
- **Logica Voice (futuro web/mobile):** LiveKit cliente, Pipecat continua orquestrando.

**Fontes:**
- [Pipecat vs LiveKit — Channel.tel](https://www.channel.tel/blog/pipecat-vs-livekit-voice-framework-decision)
- [Pipecat 1.0 release notes](https://github.com/pipecat-ai/pipecat)
- [Cekura comparison](https://www.cekura.ai/blogs/pipecat-vs-livekit-the-real-difference)

---

## 2. STT (Speech → Text): **faster-whisper + Voxtral 2 + Moonshine**

### Estratégia tiered

| Tier | Modelo | Quando usar | Tamanho |
|---|---|---|---|
| **Padrão** | **faster-whisper large-v3** | Mensagens de voz longas (WhatsApp, Telegram) | ~3GB |
| **Streaming** | **Voxtral Transcribe 2** | Conversação Logica Voice tempo real | ~4B params |
| **Edge** | **Moonshine v2** | Wake word / dispositivos limitados | 27MB |

### Por que
- **faster-whisper**: 4× mais rápido que Whisper original (CTranslate2), MIT, 99 idiomas com PT-BR perfeito. Tem port MLX otimizado (`mlx-whisper`) pro Apple Silicon do brain.
- **Voxtral Transcribe 2** (Mistral, fev/26): Apache 2.0, **5.9% WER vs 7.4% Whisper** no FLEURS, streaming nativo, 4B params, MLX port pronto.
- **Moonshine** (Useful Sensors): 27MB, roda em Raspberry Pi. Bom pra detectar "Astro" antes de ativar pipeline completo.

### Alternativas rejeitadas
- **NVIDIA Parakeet TDT 1.1B** — RTFx >2000 (mais rápido), mas só CUDA. Logica Voice tem que rodar em Mac.
- **AssemblyAI / Deepgram** — cloud paga.

**Fontes:**
- [Northflank STT benchmark 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Voxtral vs Whisper](https://weesperneonflow.ai/en/blog/2026-03-31-voxtral-whisper-open-source-speech-models-comparison-2026/)
- [Gladia STT 2026](https://www.gladia.io/blog/best-open-source-speech-to-text-models)

---

## 3. TTS (Text → Speech): **F5-TTS + Kokoro + Qwen3-TTS**

### Estratégia tiered

| Tier | Modelo | Uso | Qualidade |
|---|---|---|---|
| **Voice clone** | **F5-TTS** | Voz personalizada do CEO/agentes | ⭐⭐⭐⭐⭐ ElevenLabs-level |
| **Rápido** | **Kokoro-82M** | Respostas curtas, notificações | ⭐⭐⭐⭐ Real-time CPU |
| **Multi-lang** | **Qwen3-TTS** | PT-BR + 10 idiomas, streaming | ⭐⭐⭐⭐ |

### Por que
- **F5-TTS**: MIT, zero-shot voice cloning com 5-15s de áudio referência. Comunidade ativa, benchmark próximo de ElevenLabs.
- **Kokoro-82M**: Apache 2.0, **apenas 82M params**, real-time em CPU. Substitui ElevenLabs em respostas simples.
- **Qwen3-TTS** (Alibaba): Apache 2.0, suporta PT-BR + EN/ES/FR/DE/ZH/JA/KO/RU/IT, streaming + voice cloning.

### Considerados
- **Chatterbox** (Resemble): MIT, voice clone 5s, expressivo. Boa alternativa secundária.
- **CosyVoice2-0.5B**: emocional + streaming, mas community menor.
- **NeuTTS Air**: on-device 0.5B, primeiro TTS instant voice clone mobile.
- **Kyutai Pocket TTS** (jan/26): 100M params, roda em CPU. Atrai pra release leve.

### Alternativas rejeitadas
- **Coqui XTTS-v2**: licença **CPML não-comercial** ⛔
- **OpenVoice V2**: bom, mas F5-TTS supera em qualidade.

**Fontes:**
- [BentoML TTS comparison](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models)
- [Resemble voice cloning 2026](https://www.resemble.ai/resources/best-open-source-ai-voice-cloning-tools)
- [F5-TTS setup guide](https://localaimaster.com/blog/f5-tts-setup-guide)
- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- [Kyutai TTS](https://kyutai.org/tts)

---

## 4. Conversação contínua (modo Jarvis): **Kyutai Moshi**

### Por que
- **Único OSS com latência <200ms** speech-to-speech full-duplex (igual Gemini Live).
- Roda em **Apple Silicon via MLX** (`pip install moshi_mlx`, testado MacBook M3).
- Licenças permissivas (CC-BY 4.0 weights, Apache 2.0/MIT código).
- Suporta barge-in nativo (modelo aprendeu padrões de fala humana).
- Quick start: `python -m moshi_mlx.local_web` → web UI em `localhost:8998`.

### Como entra no Logica Voice
- **Modo padrão (Pipecat)**: STT + LLM + TTS sequencial. Latência 800ms-1.5s. Bom pra maioria.
- **Modo Jarvis (Moshi)**: speech-to-speech direto, sem texto intermediário. Latência 200ms. Pra conversação tipo Iron Man.
- Usuário toggla entre modos via `/conversa contínua on` no canal.

### Alternativas consideradas
- **Sesame CSM** (MIT, Llama-based): excelente pra multi-speaker dialogue, foco inglês. Bom upgrade futuro.
- **NVIDIA PersonaPlex**: persona/voice control + behavior learning, mas requer NVIDIA GPU.
- **DuplexCascade** (acadêmico): VAD-free, mas sem release production.
- **Sommelier** (NAVER): similar Moshi mas releases limitados.

### Limitação atual
- Moshi treinado mais em inglês. PT-BR funciona mas tom soa "robótico". Workaround: usar Moshi pra wake word + estado, transferir pra Pipecat tradicional pra resposta longa em PT.

**Fontes:**
- [Moshi GitHub](https://github.com/kyutai-labs/moshi)
- [Moshi MLX install (Apple Silicon)](https://anil.recoil.org/notes/kyutai-streaming-voice-mlx)
- [Why Moshi could replace Whisper](https://scalastic.io/en/moshi-stt-vs-whisper/)
- [Moshi vs OpenAI Realtime — DeepLearning.ai](https://www.deeplearning.ai/the-batch/moshi-an-open-alternative-to-openais-realtime-api-for-speech/)
- [Sesame CSM-1b alternativa ElevenLabs](https://medium.com/data-science-in-your-pocket/sesame-csm-1b-more-than-tts-elevenlabs-free-alternative-b1a3bdffcea2)

---

## 5. WhatsApp: **Baileys** (MIT)

### Por que
- WebSockets-based, sem Selenium/browser. Roda headless.
- Multi-device oficial do WhatsApp.
- Comunidade ativa, `@whiskeysockets/baileys` mantida.
- LogicaOS já usa em `channels/whatsapp/bot.js` — só refatorar pro adapter pattern.

### Considerado
- **Evolution API**: dual-connection (Baileys + Cloud API), 10+ integrações. Bom como alternativa hosted, mas adiciona infra (Node + Postgres).
- **WhatsApp Cloud API oficial**: paga, mas mais estável. Adapter opcional pra produção crítica.

**Fontes:**
- [Baileys GitHub](https://github.com/WhiskeySockets/Baileys)
- [Evolution API](https://github.com/evolution-foundation/evolution-api)

---

## 6. Telegram: **Telegraf / GramJS**

### Por que
- LogicaOS já usa Telegram Bot API via fetch direto. Telegraf adiciona conveniências (middleware, sessions, scenes) sem peso.
- GramJS pra MTProto (acesso a conta de usuário, não só bot) — opcional pra features avançadas.

### Já existe no LogicaOS
- `channels/telegram/bot.js` — refatorar pro adapter pattern.

---

## 7. Memória: **pgvector + Chroma (embedded)**

### Estratégia dupla

| Modo | Tech | Quando |
|---|---|---|
| **Server** (LogicaOS instalação completa) | **pgvector** (Supabase) | Já existe no brain. Vetorial + relacional num só. |
| **Standalone** (cliente solo, sem Supabase) | **Chroma embedded** | Zero infra, roda no mesmo processo Node/Python. |

### Por que essas
- **pgvector**: até 20-30M vetores. Bom enquanto LogicaOS estiver na escala de "uma empresa".
- **Chroma embedded**: deploy zero-friction. `npx logica-voice init` cria DB local.
- **Qdrant**: opcional pra escala (>30M vetores). Adapter já pronto via LangChain/LlamaIndex.

### Rejeitados
- **Pinecone**: SaaS, paga, vendor lock-in.
- **Weaviate**: mais pesado que Qdrant pro mesmo job.
- **Milvus**: scale-out monstro, overkill pra 99% dos casos.

**Fontes:**
- [Best vector DBs 2026](https://www.pingcap.com/compare/best-vector-database/)
- [Qdrant vs Chroma](https://www.kunalganglani.com/blog/qdrant-vs-chroma)

---

## 8. Multi-agent: **LogicaOS Synapses (existente)**

### Por que não AutoGen/CrewAI/LangGraph
- **AutoGen**: Microsoft moveu pra "maintenance mode" em out/25 — agora é Microsoft Agent Framework. Risco de fork morrer.
- **CrewAI**: bom pra setup rápido mas opinionated demais (roles+goals fixos).
- **LangGraph**: forte mas LangChain stack vem com peso.

**LogicaOS já tem o orquestrador:**
- `synapses/orchestrator.js` — runChain, agents+chains+squads
- `synapses/llm-router.js` — roteamento inteligente Claude vs MLX vs Qwen
- `synapses/memory-hub.js` — memória semântica/episódica/procedural
- 130+ agentes catalogados

Logica Voice **NÃO reinventa** o orchestrator — é a **camada de canais** acima dele.

### Mas vou estudar
- **Microsoft Agent Framework** (sucessor AutoGen, out/25) — pode trazer padrões maduros.
- **AG2** (fork comunidade do AutoGen) — boa pra conversational patterns.
- **Dify** (self-hosted LLM app platform) — referência de UX visual.

**Fontes:**
- [AG2 / Microsoft Agent Framework](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks)
- [CrewAI / LangGraph comparison](https://www.lindy.ai/blog/best-ai-agent-frameworks)

---

## Comparação econômica (mensal, uso médio)

| Item | Cloud equivalente | Logica Voice | Economia |
|---|---:|---:|---:|
| TTS (200k chars/mês) | ElevenLabs Creator: **$22** | Kokoro/F5 local: **$0** | $22 |
| STT (10h áudio/mês) | OpenAI Whisper API: **$3.60** | faster-whisper local: **$0** | $3.60 |
| LLM (Claude Sonnet médio) | Anthropic: **$50-200** | Qwen3-30B MLX local: **$0** (ou $50 cloud) | $50-200 |
| Voice conv. (Gemini Live) | $50-150 estimado | Moshi local: **$0** | $50-150 |
| Vector DB | Pinecone Starter: **$70** | pgvector ou Chroma: **$0** | $70 |
| **Total** | **~$195-445/mês** | **~$0-50/mês** (cloud opt-in) | **~$195-395/mês** |

Economia pra cliente médio: ~$2.500/ano. Pra agência multi-cliente: $25k+/ano.

---

## TL;DR (a stack final)

```yaml
orchestration: Pipecat 1.0
stt:
  default: faster-whisper (large-v3 MLX)
  streaming: Voxtral Transcribe 2
  edge: Moonshine v2
llm:
  local: Qwen3-30B MLX (já no brain)
  cloud_optional: Claude/Gemini via LogicaProxy
tts:
  voice_clone: F5-TTS
  fast: Kokoro-82M
  multilang: Qwen3-TTS
voice_continuous: Kyutai Moshi (MLX)
memory:
  server: pgvector (Supabase)
  standalone: Chroma embedded
channels:
  whatsapp: Baileys (existente)
  telegram: Telegraf (refator)
  voice: Pipecat + WebRTC
  web: dashboard React (existente)
multi_agent: LogicaOS Synapses (existente)
```
