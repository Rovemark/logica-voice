# LogicaOS Integration

Logica Voice é **independente** — funciona sozinho com qualquer brain. Mas é também **bundled na instalação do LogicaOS** (a partir de v1.9.123+), com integração first-class aos 130+ agentes.

**Princípio chave:** não substitui nada que já existe. Adiciona como **alternativa opt-in**.

---

## Bundling: como vai no installer LogicaOS

### Estrutura

```
~/LogicaOS/                          # raiz do LogicaOS instalado
├── synapses/                        # brain (existente, intocado)
├── channels/
│   ├── telegram/bot.js              # CONTINUA EXISTINDO E FUNCIONANDO
│   └── whatsapp/bot.js              # CONTINUA EXISTINDO E FUNCIONANDO
├── apps/voice/                      # LogicaOS Voice app (continua)
├── skills/elevenlabs/               # ElevenLabs skill (continua)
└── conversational/                  # 🆕 LOGICA CONVERSATIONAL bundled
    ├── packages/
    │   ├── core/                   # orquestrador próprio (TS)
    │   ├── adapters/               # WA, TG, Voice, Web
    │   ├── voice/                  # pipeline áudio
    │   └── cli/
    ├── config/
    │   ├── agents.yaml             # built-in agents (se sem LogicaOS)
    │   └── voices.yaml             # voice cloning configs
    └── package.json
```

### Setup wizard pergunta

```
═══ SETUP: Logica Voice ═══

Logica Voice é o framework conversacional open source bundled
com o LogicaOS. Adiciona:
  • WhatsApp e Telegram refatorados (mesma funcionalidade, mais robustez)
  • Voz local 100% free (Kokoro, F5-TTS, faster-whisper)
  • Modo Jarvis (conversação contínua tipo Iron Man)
  • Voice cloning local

Pode ser ativado SEM remover ElevenLabs ou LogicaOSVoice atual.

Ativar Logica Voice? [Y/n] ▍
```

### Se aceitar (Y):
- Instala `conversational/` (~80MB code + ~3GB models opcionais)
- Configura brain adapter `logicaos` apontando pra `localhost:3001`
- Adiciona PM2 process `logica-conv` (não substitui `telegram` / `whatsapp` existentes)
- Cliente decide depois qual usar (toggle no dashboard)

### Se recusar (n):
- Não instala nada novo
- LogicaOS funciona exatamente como antes
- Pode ativar depois: `node setup.js --activate-conversational`

---

## Coexistência: o que rola em paralelo

```
PM2 processes (após instalação completa):
├── synapses-api        (brain existente, intocado)
├── mind                (existente)
├── ambient-monitor     (existente)
├── cron-runner         (existente)
├── world-model-sync    (existente)
├── logicaproxy         (existente)
├── telegram            (legacy — continua se cliente prefere)
├── whatsapp            (legacy — continua se cliente prefere)
└── logica-conv         (🆕 novo — opt-in, pode rodar paralelo)
```

**Cenário 1: Cliente usa só legacy (default no upgrade)**
- `telegram` e `whatsapp` legacy processam mensagens
- `logica-conv` instalado mas idle
- Zero mudança no comportamento

**Cenário 2: Cliente migra pro Logica Conv (escolhe no dashboard)**
- Toggle: "Usar Logica Voice nos canais"
- `telegram` e `whatsapp` legacy entram em modo passivo (não respondem)
- `logica-conv` assume os canais
- Migração pode reverter a qualquer momento

**Cenário 3: Cliente híbrido (testa em 1 canal)**
- Telegram = Logica Conv (testando)
- WhatsApp = legacy (estável)
- Migra um canal por vez sem risco

---

## ElevenLabs e LogicaOSVoice — não saem

### ElevenLabs
- Continua disponível em `skills/elevenlabs/`
- Skill autorizada pra Astro, Story, Cleo, Voice, Vibe (como hoje)
- Pode ser usado **paralelo** com Kokoro/F5-TTS do Logica Conv
- Cliente que paga ElevenLabs e prefere qualidade ELevenLabs → continua usando

### LogicaOSVoice (app Mac/Win existente)
- Continua sendo o app desktop principal
- Continua se conectando ao brain via API atual
- Logica Voice **adiciona** um WebSocket adicional pro pipeline novo
- App pode escolher: pipeline antigo (REST) OU novo (WebSocket Logica Conv)
- Toggle no Settings do app

### Configuração

`config/voice-config.yaml`:
```yaml
# Voz do dashboard / chat textual
dashboard_voice:
  provider: kokoro      # ou elevenlabs (continua se cliente tem key)

# Voz do LogicaOS Voice app
desktop_voice:
  legacy_mode: true     # usa pipeline antigo (REST + ElevenLabs/TTS atual)
  # OU:
  legacy_mode: false    # usa Logica Voice
  provider: f5-tts      # com voice clone do dono
  fallback: elevenlabs  # se f5-tts falhar, cai pra ElevenLabs (se key existe)

# Voz pra anúncios (release-announcer, alertas)
notification_voice:
  provider: kokoro      # rápido, free
```

---

## Brain adapter "logicaos" — first-class

Logica Voice vem com adapter LogicaOS pré-configurado **quando bundled**:

```yaml
# conversational/config.yaml (gerado pelo setup)
brain:
  provider: logicaos
  url: http://localhost:3001
  api_key: ${BRAIN_API_KEY}     # do .env do LogicaOS (compartilhado)
  default_agent: aurora          # ou whatever foi configurado no setup do LogicaOS
  
  # Mention routing automático
  mentions_enabled: true         # @luna, @dev, @cleo, etc
  squad_commands: true           # /squad hackers, /squad globe
  chain_commands: true           # /chain lancamento
```

### Recursos automaticamente disponíveis:
- **130+ agentes** acessíveis via `@nome` em qualquer canal
- **59 clones mentores** via `@steve-jobs`, `@bourdain`, etc
- **17 squads** via `/squad <nome>`
- **Chains** via `/chain <nome>`
- **Memória pgvector** persistente cross-channel
- **Smart router** (Claude/MLX/Qwen automático)

---

## Migração: legacy → Logica Conv (passo-a-passo)

Pra clientes existentes do LogicaOS que querem migrar:

### Fase 1: instalação lado-a-lado (zero risco)
```bash
node update.js                         # update LogicaOS pra v1.9.123+
node setup.js --activate-conversational # opt-in Logica Conv
pm2 list                                # vê os 2 telegram (legacy + new), idle
```

### Fase 2: teste em 1 canal
```bash
# Dashboard → Settings → Conversational → Test on Telegram
# Toggle: Telegram via Logica Conv = ON
# WhatsApp continua legacy
```

Cliente testa 1 semana. Se OK, migra WhatsApp também. Se não, desativa.

### Fase 3: full migration
```bash
# Dashboard → Settings → Conversational → Activate all channels
# Legacy processes ficam em standby
```

### Fase 4 (futura): deprecar legacy
- v2.0 LogicaOS: legacy `channels/{whatsapp,telegram}` removidos (Logica Conv vira default)
- Cliente que ainda usa legacy é avisado 6 meses antes
- Migração assistida pelo CLI

---

## Compartilhamento de recursos com LogicaOS

Quando bundled, Logica Conv reusa do LogicaOS:

| Recurso | Compartilhado | Razão |
|---|---|---|
| `.env` | ✅ | Mesmas credenciais (Anthropic, Telegram token, etc) |
| Supabase / pgvector | ✅ | Memória unificada |
| LogicaProxy (OAuth Claude) | ✅ | Brain compartilha proxy |
| MLX models (Qwen3-30B) | ✅ | Já baixados pelo LogicaOS |
| `config/owner.yaml` | ✅ | Identidade do dono |
| PM2 ecosystem | ✅ | Adiciona processo, não cria PM2 novo |

| Recurso | Próprio do Logica Conv | Razão |
|---|---|---|
| `conversational/config.yaml` | ✅ | Specific do conversacional |
| Voices (`voices.yaml`, embeddings) | ✅ | F5-TTS embeddings locais |
| Adapters (WA, TG, Voice) | ✅ | Refator do código legacy |
| Audio pipeline (Pipecat-like) | ✅ | Inovação central |

---

## Sem LogicaOS: funciona igual?

Sim. Logica Voice é standalone. Quando usado sem LogicaOS:
- Brain adapter padrão é `built-in` (carrega `agents.yaml` local)
- OU plugue OpenAI/Claude/Gemini/Ollama
- Memória usa Chroma embedded (não precisa Supabase)
- Tudo o resto idêntico

**Adoption funnel:**
```
Usuário descobre Logica Conv (open source) → 
  usa standalone com OpenAI →
    quer mais agents prontos →
      conhece LogicaOS →
        instala LogicaOS → 
          Logica Conv vira bundled, ganha 130+ agentes
```

LogicaOS ganha distribuição via Logica Conv. Logica Conv ganha brand via LogicaOS.

---

## Comparativo: standalone vs bundled

| Feature | Standalone | Bundled c/ LogicaOS |
|---|---|---|
| Custo | $0 (free) | LogicaOS é licença paga (Logica Conv free dentro) |
| Setup | `npx create-logica-voice` | Já vem no installer LogicaOS |
| Brain | OpenAI/Claude/etc | LogicaOS Synapses (130+ agentes) |
| Agentes prontos | Defina em `agents.yaml` | 130+ pre-built |
| Squads/Chains | Não | Sim (17 squads, várias chains) |
| Clones mentores | Não | 59 (Jobs, Bourdain, Dalio, etc) |
| Memória | Chroma embedded | pgvector Supabase |
| ElevenLabs | Opt-in via adapter | Continua disponível como skill |
| Voice (Mac/Win app) | Bring your own | LogicaOSVoice integrado |
| Updates | `npm update logica-conv` | Via `update.js` do LogicaOS |

---

## FAQ

**Q: Vai forçar todo cliente LogicaOS a usar Logica Conv?**
A: Não. Setup pergunta. Cliente pode recusar e continuar com legacy infinitamente.

**Q: ElevenLabs vai parar de funcionar quando eu ativar Logica Conv?**
A: Não. ElevenLabs skill continua disponível. Você pode usar ELevenLabs DENTRO do Logica Conv (adapter `elevenlabs` como TTS).

**Q: LogicaOS Voice app vai parar de funcionar?**
A: Não. App continua. Você pode escolher: pipeline antigo (REST) ou novo (WebSocket Logica Conv). Settings do app tem toggle.

**Q: Meu .env vai ser modificado quando ativar?**
A: Apenas adicionado: novas chaves `CONVERSATIONAL_*`. Nada existente removido/alterado.

**Q: Cliente sem LogicaOS pode contribuir pro Logica Conv?**
A: Sim. Repo separado (`Rovemark/logica-voice`), MIT, contribs welcome sem CLA.

**Q: Logica Conv vai ter telemetria?**
A: Não silenciosa. Opt-in explícito no setup. Você decide se reportar uso.

**Q: Quanto vai custar?**
A: Logica Voice é $0, sempre. Single binary, MIT. LogicaOS é separado (licença paga). Cliente paga LogicaOS pelos agentes prontos + brain + skills, não pela camada conversacional.
