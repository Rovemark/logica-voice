# Architecture Decision Records (ADRs)

Decisões com tradeoff conscientes. Cada uma documenta: contexto, alternativas, escolha, consequência.

---

## ADR-001: Construir orquestrador próprio (não usar Pipecat direto)

**Contexto:** Pipecat (BSD-2, Daily.co) é o framework referência pra orquestração de voz streaming. Faz sentido usar diretamente como dependência?

**Alternativas:**
1. **Usar Pipecat direto** como dependência Python.
2. **Construir próprio em TypeScript** inspirado em Pipecat.
3. **Construir próprio em Python** (mesma stack, mas controle total).
4. **Fork de Pipecat** (continuar evolução comunidade-driven).

**Decisão:** **Construir próprio em TypeScript**, com Pipecat como referência arquitetural.

**Razão:**
- **Linguagem:** canais (Baileys/WhatsApp, Telegraf/Telegram) são JS nativos. Ter Python no meio força subprocess ou microservice complicado.
- **Bundling:** LogicaOS é Node — bundling Logica Conv vai natural se também for Node.
- **Identidade do produto:** "Pipecat brasileiro" tem narrativa forte. Forkear Pipecat só seria fork, não produto.
- **Controle:** podemos adicionar canais (WA/TG) como first-class citizens, multi-agent built-in, brain abstractions.

**Consequência:**
- ✅ Stack uniforme TS (canais + orchestrator + dashboard)
- ✅ Bundling LogicaOS trivial
- ✅ Liberdade total de design (canais, brain adapters, modo Jarvis)
- ⚠️ Reinventa parte do trabalho que Pipecat já fez (mitigation: ler código deles abertamente, replicar patterns testados)
- ⚠️ STT/TTS Python (faster-whisper, F5-TTS) precisam subprocess ou WebSocket bridge

---

## ADR-002: Moshi (Kyutai) pra modo Jarvis (opcional, não substitui pipeline normal)

**Contexto:** queremos conversação contínua estilo Gemini Live (latência <300ms, full-duplex).

**Alternativas:**
1. **Moshi (Kyutai)** — 200ms, full-duplex, Apache+CC-BY, MLX disponível.
2. **Sesame CSM-1b** (MIT) — TTS conversacional, não full-duplex.
3. **PersonaPlex (NVIDIA)** — full-duplex + persona, só CUDA.
4. **DuplexCascade** (acadêmico) — sem release.

**Decisão:** **Moshi** como modo opt-in (toggle), não substitui pipeline padrão.

**Razão:**
- Moshi tem inteligência embarcada (speech foundation) — não usa o brain LogicaOS.
- Pra multi-agent, tools, análises: pipeline padrão (STT→LLM→TTS) é melhor.
- Moshi brilha em "Astro, qual a hora?" sem botão.

**Consequência:**
- ✅ Latência <200ms quando user quer
- ✅ Pipeline padrão continua dono do fluxo normal
- ⚠️ 2 pipelines paralelos (mantenção dupla, mitigation: isolar via toggle limpo)
- ⚠️ Moshi treinado mais em EN — PT-BR robótico (mitigation: usar pra wake + curto)

---

## ADR-003: faster-whisper + Voxtral + Moonshine (STT tiered)

**Contexto:** STT serve mensagens longas (WhatsApp voice), streaming (live voice), e wake word.

**Alternativas:**
1. faster-whisper large-v3 — 7.4% WER, 99 idiomas, MLX.
2. Voxtral Transcribe 2 (Mistral, fev/26) — 5.9% WER, streaming, Apache 2.0.
3. NVIDIA Parakeet TDT — fastest, só CUDA.
4. Moonshine v2 — 27MB edge.

**Decisão:** **Tiered.** faster-whisper default, Voxtral streaming, Moonshine wake.

**Razão:** sem "melhor pra tudo" — cada tier serve nicho específico.

**Consequência:** ~5GB modelos baixados, configuração via tier.

---

## ADR-004: F5-TTS + Kokoro + Qwen3-TTS (TTS tiered) + ElevenLabs opt-in

**Contexto:** TTS precisa de qualidade (voice clone), velocidade (resposta curta), PT-BR.

**Alternativas:**
1. F5-TTS — voice clone qualidade ElevenLabs, MIT.
2. Kokoro-82M — real-time CPU, Apache 2.0.
3. Qwen3-TTS — PT-BR nativo, Apache 2.0.
4. Chatterbox — voice clone 5s, MIT.
5. ElevenLabs — pago, qualidade premium.
6. Coqui XTTS-v2 — bom mas **licença CPML não-comercial** ⛔.

**Decisão:** **Tiered local** (F5/Kokoro/Qwen3-TTS) **+ ElevenLabs como adapter opt-in**.

**Razão:**
- Filosofia 100% free local default.
- ElevenLabs preservado: clientes LogicaOS que já têm key continuam usando.
- Cliente escolhe trade-off qualidade vs custo.

**Consequência:**
- ✅ Free default
- ✅ ElevenLabs respect (não destrói investimento de clientes)
- ⚠️ ~6GB modelos baixados (mitigation: download on-demand)

---

## ADR-005: Brain agnóstico — adapter pattern (não acoplado a LogicaOS)

**Contexto:** Logica Conv deve ser independente (standalone) e bundled com LogicaOS.

**Alternativas:**
1. **Brain hardcoded LogicaOS** — dependência fixa.
2. **Brain abstration via adapter** — qualquer brain plugável.
3. **Multi-brain (por agente)** — cada agente seu brain.

**Decisão:** **Brain adapter pattern.** LogicaOS é UM dos adapters (first-class), mas não obrigatório.

**Razão:**
- Logica Conv independente abre adoção comunidade (sem precisar comprar LogicaOS).
- LogicaOS ganha distribuição via Logica Conv standalone que migra pra bundled.
- Permite OpenAI/Claude/Ollama/MLX/custom.

**Consequência:**
- ✅ Distribuição open source ampla
- ✅ LogicaOS continua valor agregado (130+ agents, squads, chains)
- ⚠️ Mais código pra testar (vários adapters)

---

## ADR-006: pgvector default (quando bundled) + Chroma fallback (standalone)

**Contexto:** memória semântica precisa vector DB.

**Alternativas:**
1. pgvector (Supabase) — bundled LogicaOS já tem.
2. Qdrant — escalável.
3. Chroma embedded — zero infra.
4. Pinecone — SaaS pago.

**Decisão:** **pgvector quando bundled, Chroma quando standalone, Qdrant opcional avançado.**

**Razão:** standalone precisa zero-friction; bundled aproveita infra existente.

---

## ADR-007: WhatsApp via Baileys (não Cloud API oficial)

**Contexto:** WhatsApp tem Baileys (free WS) vs Cloud API oficial (paga).

**Decisão:** **Baileys default, Cloud API adapter opt-in.**

**Razão:** 100% free filosofia + Cloud API disponível pra produção crítica.

**Consequência:** ⚠️ Baileys gray-area ToS (risk de ban, mas usado em produção amplamente).

---

## ADR-008: Identidade unificada via `contacts` table

**Decisão:** **Table `contacts` com `identities[]`** (já no LogicaOS schema).

**Razão:** cross-channel memory funciona naturalmente.

---

## ADR-009: TypeScript no core (vs Python)

**Já justificado no ADR-001.** Decisão: TypeScript.

---

## ADR-010: Wake word — OpenWakeWord (MIT)

**Alternativas:** Picovoice Porcupine (free dev, pago prod), OpenWakeWord (MIT), Snowboy (morto).

**Decisão:** **OpenWakeWord.**

**Razão:** 100% free filosofia. Qualidade aceitável.

---

## ADR-011: Bundling com LogicaOS (sem substituir nada existente)

**Contexto:** LogicaOS já tem `channels/telegram/bot.js`, `channels/whatsapp/bot.js`, LogicaOS Voice app, ElevenLabs skill. Como Logica Conv entra?

**Alternativas:**
1. **Substituir tudo** — agressivo, quebra clientes existentes.
2. **Coexistir lado-a-lado** — Logica Conv como opt-in, legacy continua.
3. **Só standalone** — clientes LogicaOS instalam Logica Conv separado.

**Decisão:** **Coexistir lado-a-lado.** Logica Conv bundled na instalação do LogicaOS v1.9.123+ como **opt-in**. Legacy `channels/*` e ElevenLabs continuam funcionando intactos.

**Razão:**
- **Zero risco** pra clientes existentes na migração v1.9.122 → v1.9.123.
- **Adoção gradual** — cliente testa em 1 canal, migra resto no próprio ritmo.
- **ElevenLabs respect** — cliente que paga ElevenLabs e quer continuar tem direito.
- **LogicaOS Voice app** continua funcionando com pipeline antigo OU novo (toggle no app).

**Consequência:**
- ✅ Adoção sem fricção
- ✅ Cliente escolhe quando migrar
- ⚠️ Duas implementações coexistem (mais código pra suportar)
- ⚠️ Confusão UI (qual canal usa qual pipeline?) — mitigation: dashboard mostra claramente

---

## ADR-012: Logica Conv tem multi-agent próprio (não força LogicaOS)

**Contexto:** quando usado standalone (sem LogicaOS), como suportar multi-agent?

**Alternativas:**
1. **Sem multi-agent** — 1 agente só.
2. **`agents.yaml` local** — define agentes em YAML.
3. **Forçar LogicaOS** — multi-agent só com LogicaOS.

**Decisão:** **`agents.yaml` local + adapter LogicaOS opcional.**

**Razão:**
- Maioria dos casos precisa de multi-agente.
- YAML simples cobre 80% dos casos pessoais/PMEs.
- LogicaOS adapter dá superpoderes (130+ agents, chains, squads).

**Consequência:**
- ✅ Standalone usável de verdade
- ✅ LogicaOS continua valor agregado
- ⚠️ Lógica de routing (mention `@agent`) precisa funcionar nos 2 modos

---

## ADR-013: TypeScript monorepo (pnpm workspaces)

**Contexto:** Logica Conv tem múltiplos packages (core, adapters, voice, cli).

**Alternativas:**
1. Monorepo Turborepo
2. Monorepo Nx
3. **Monorepo pnpm workspaces** (lightweight)
4. Múltiplos repos

**Decisão:** **pnpm workspaces** (single repo).

**Razão:**
- Single repo = facilita PRs comunidade.
- pnpm workspaces = leve, sem overhead Turborepo/Nx.
- Compartilha types entre packages naturalmente.

**Estrutura:**
```
packages/
├── core/           # frames, pipeline, brain adapter interface
├── adapters/
│   ├── whatsapp/   # Baileys
│   ├── telegram/   # Telegraf
│   ├── voice/      # WebSocket + pipeline
│   └── web/        # WebSocket
├── voice/
│   ├── stt/        # faster-whisper, voxtral wrappers
│   ├── tts/        # kokoro, f5, elevenlabs wrappers
│   └── moshi/      # Jarvis mode
├── brain/
│   ├── openai/
│   ├── anthropic/
│   ├── gemini/
│   ├── ollama/
│   ├── mlx/
│   ├── logicaos/
│   └── built-in/
└── cli/            # logica-conv CLI
```

---

## ADR-014: Distribuição — npm + Homebrew + Docker

**Contexto:** como o usuário instala?

**Decisão:**
- **`npx create-logica-voice` (npm)** — standalone, most common
- **`brew install logica-conv`** — Mac CLI direto
- **Docker compose** — server/VPS deploy
- **Bundled no LogicaOS installer** — automatic pra clientes LogicaOS

---

## ADR-015: Sem CLA (Contributor License Agreement)

**Contexto:** projeto open source, como aceitar contribuições?

**Alternativas:**
1. CLA (cede direitos)
2. DCO (Developer Certificate of Origin)
3. **Nenhum** (MIT puro, sem strings)

**Decisão:** **Nenhum.** MIT puro. Contributor mantém direitos, apenas garante MIT da contrib.

**Razão:**
- Fricção zero pra comunidade.
- Logica Conv não vai fechar — Rovemark não precisa rights pra relicensar.
- Confiança da comunidade > controle.

---

## ADRs pendentes

- **ADR-016:** Telemetria — coletar uso anônimo opt-in?
- **ADR-017:** Plugin system — npm packages externos?
- **ADR-018:** Multi-tenant — workspace isolation pra SaaS?
- **ADR-019:** Pricing model — totalmente free? Sponsorware?
- **ADR-020:** Branding — site, logo, manifesto público
