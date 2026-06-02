# VOICES — Sistema voice-per-agent

> **Cada agente, cada clone, cada persona — voz própria, coerente, configurável.**
> Tier 1 auto-assign · Tier 2 record · Tier 3 import. 100% local. Free. Ética first.

---

## A visão

Identidade de um agente não é só nome + system prompt. **A voz é parte da identidade.** Se Aurora (CEO) responde com a mesma voz hardcoded "Brian masculina" que Cleo (copywriter) e Steve Jobs (clone mentor), você perde a magia.

Logica Voice resolve isso com um sistema único: **mapping declarativo de voz por agente**, baseado em 3 tiers de complexidade/qualidade.

```yaml
# config/voices.yaml
voices:
  aurora:
    provider: f5-tts
    embedding: voices/aurora.npy
    
  cleo:
    provider: kokoro
    voice_id: af_bella
    speed: 1.05
    
  steve-jobs:
    provider: f5-tts
    embedding: voices/clones/steve-jobs.npy
```

Brain manda texto → Logica Voice lookup voz → TTS sintetiza → áudio sai com personalidade.

---

## Os 3 tiers

### 🥉 Tier 1 — Auto-assign (Kokoro)

**Pra:** todos os agentes do projeto, default.
**Setup:** 0 trabalho. Roda no `npx setup`.
**Custo:** $0.
**Qualidade:** boa pra notificações, respostas curtas, conversa cotidiana.

**Como funciona:**

Logica Voice lê metadados de cada agente (`gender`, `personality`, `role`) e auto-atribui uma voz Kokoro do pool.

Pool default:
```yaml
kokoro_pool:
  female:
    sky:      { description: "feminina, jovem, neutra" }
    bella:    { description: "feminina, energética, criativa" }
    sarah:    { description: "feminina, profissional, calma" }
    nicole:   { description: "feminina, técnica, precisa" }
    sky2:     { description: "feminina, narrativa" }
  male:
    michael:  { description: "masculino, técnico, neutro" }
    liam:     { description: "masculino, expressivo" }
    will:     { description: "masculino, assertivo" }
    george:   { description: "masculino, calmo, profissional" }
    fenrir:   { description: "masculino, grave, dramático" }
  neutral:
    river:    { description: "neutro, suave" }
```

**Regras de auto-assign:**
```typescript
function autoAssignVoice(agent) {
  const gender = agent.gender || inferGender(agent.name); // PT-BR heuristic
  const personality = agent.personality?.toLowerCase() || '';

  if (gender === 'female') {
    if (/energ|criativ|copy/.test(personality)) return 'kokoro/bella';
    if (/calm|professional/.test(personality))  return 'kokoro/sarah';
    if (/técnic|preciso/.test(personality))     return 'kokoro/nicole';
    return 'kokoro/sky';
  }
  if (gender === 'male') {
    if (/assertiv|vendas/.test(personality))    return 'kokoro/will';
    if (/expressiv|criativ/.test(personality))  return 'kokoro/liam';
    if (/dramatic|grave/.test(personality))     return 'kokoro/fenrir';
    if (/técnic|engenh/.test(personality))      return 'kokoro/michael';
    return 'kokoro/george';
  }
  return 'kokoro/river';
}
```

**Output:** todos os 130+ agentes têm voz coerente sem você mexer em nada.

---

### 🥈 Tier 2 — Record (sua voz, voz da marca)

**Pra:** ~10-20 "star agents" (C-Suite, CEO, marca da empresa).
**Setup:** ~3 minutos por voz.
**Custo:** $0.
**Qualidade:** **idêntica a ElevenLabs** (F5-TTS é state-of-art OSS).

**Como funciona:**

```bash
$ logica voice record aurora

🎙 Voice cloning — Aurora (CEO)

Você vai gravar 10-15 segundos de áudio referência.
Recomendações:
  • Ambiente silencioso
  • Fale naturalmente, com a entonação que quer pro agente
  • Pode ler qualquer texto

Quando pronto, pressione SPACE pra começar.
SPACE pra parar.

[esperando...] ⏸
[gravando]    ▮▮▮▮▮▮▮▮ 12s
✓ Gravação OK (qualidade: excelente)

🔄 Gerando embedding F5-TTS...
✓ Embedding salvo em config/voices/aurora.npy (487KB)

🎵 Teste:
  Aurora: "Olá Andre, sou eu, pronta pra ajudar."
  [playback]
  
? Ficou bom? [Y/n/regravar] Y

✓ Voz registrada. Pronto pra usar em qualquer canal.
```

**Atribuição múltipla:**
```yaml
# Mesma voz pra vários agentes (ex: voz do dono como Astro + Aurora)
aurora:
  provider: f5-tts
  embedding: voices/dono.npy
  
astro:
  provider: f5-tts
  embedding: voices/dono.npy  # mesma voz
```

**Quando recomendar Tier 2:**
- CEO/Aurora do dono (personaliza ele)
- Personagens recorrentes (marca)
- Agentes "ponta-de-lança" que falam mais com o usuário

---

### 🥇 Tier 3 — Import (clones de mentores)

**Pra:** clones inspirados em pessoas reais (Steve Jobs, Bourdain, Hormozi).
**Setup:** ~5 minutos por clone.
**Custo:** $0.
**Qualidade:** autêntica — voz real do mentor.

**Como funciona:**

```bash
$ logica voice import-clone steve-jobs --source youtube --url <wwdc-keynote-url>

⚠️ AVISO LEGAL (importante)

Voice cloning de pessoas reais pode infringir:
  • Direitos de personalidade (BR Art. 20 CC, US right of publicity)
  • Direitos autorais sobre a gravação fonte
  • Termos de uso da plataforma fonte (YouTube ToS)

Usos LEGÍTIMOS comuns:
  ✓ Personagem fictício inspirado (sem imitação comercial direta)
  ✓ Uso educacional/paródia (varia por jurisdição)
  ✓ Pessoa pública com áudio em domínio público
  ✓ Você mesmo (sua própria voz)
  ✓ Pessoa que deu consentimento explícito

Usos ARRISCADOS:
  ✗ Fingir que pessoa real disse algo que não disse
  ✗ Uso comercial sem licença do clonado
  ✗ Deepfake malicioso (crime em vários países)

Confirma que o uso é legítimo? [y/N] y

🔄 Baixando áudio fonte (YouTube)...
✓ Áudio baixado (8 MB)
🔄 Extraindo 15s limpos (VAD + denoise)...
✓ Trecho extraído
🔄 Gerando embedding F5-TTS...
✓ Embedding salvo em config/voices/clones/steve-jobs.npy

🎵 Teste:
  Steve Jobs (clone): "Hello. Today we're announcing something amazing."
  [playback]
  
? Aprovar? [Y/n] Y

✓ Clone steve-jobs configurado.
```

**Fontes suportadas:**
```bash
logica voice import-clone <slug> --source youtube --url <url>
logica voice import-clone <slug> --source file --path <audio.wav>
logica voice import-clone <slug> --source url --url <https://...mp3>
logica voice import-clone <slug> --source spotify --track <id>  # via API
logica voice import-clone <slug> --source podcast --rss <feed>  # extrai episódio
```

**Batch import (pros 59 clones do LogicaOS):**
```bash
$ logica voice import-clones --from clones/*/IDENTITY.md --confirm-all

⚠️ Vai importar 59 clones de fontes públicas. Confirme leu o aviso legal acima.
Continuar? [y/N] y

[1/59] steve-jobs    → WWDC 2007 keynote (Apple oficial)       ✓
[2/59] bourdain      → Parts Unknown S04E03 (CNN trailer)       ✓
[3/59] hormozi       → My First Million podcast clip (oficial)  ✓
...
[59/59] tavis-ormandy → DEF CON 28 talk (DEF CON YouTube)        ✓

✓ 59 clones importados. Tempo: 4h 12min.
```

---

## Sistema de pickers (override por turno)

Mesmo com voz configurada, dá pra trocar pontualmente:

```
User: "Astro, leia esse texto com a voz da Luna"
Brain detecta override → temporariamente usa voz da Luna pra essa resposta.

User: "Conte essa história como o Bourdain"
Brain detecta → usa voz do clone Bourdain.
```

Configurável via comando ou wake-phrase:
```yaml
voice_overrides:
  enabled: true
  wake_phrases:
    - "leia com a voz d{a,o} (\\w+)"  # "leia com a voz da Luna"
    - "fal{a,e} como (\\w+)"          # "fale como Bourdain"
    - "(\\w+) responde"               # "Luna responde"
```

---

## Per-channel voice (avançado)

Mesma agent, vozes diferentes por canal:

```yaml
aurora:
  default:
    provider: f5-tts
    embedding: voices/aurora-clone.npy
  
  per_channel:
    whatsapp:
      provider: kokoro          # WA voz curta default
      voice_id: af_sarah
    
    voice-desktop:
      provider: f5-tts          # app desktop voz premium
      embedding: voices/aurora-clone.npy
    
    telegram:
      provider: qwen3-tts       # Telegram precisa PT-BR forte
      voice_id: pt-br-female
```

Razão: WhatsApp tem limite de 1MB audio, Kokoro gera mais compacto. Desktop pode ter qualidade max.

---

## Configuração avançada por voz

```yaml
aurora:
  provider: f5-tts
  embedding: voices/aurora.npy
  
  # Tuning fino (opcional)
  speed: 1.0              # 0.5-2.0
  pitch_shift: 0          # -12 a +12 semitones
  energy: 1.0             # 0.5-2.0 (intensidade)
  
  # SSML hints
  emphasis: moderate      # none | reduced | moderate | strong
  prosody:
    rate: medium
    volume: medium
  
  # Sample rate output
  sample_rate: 24000      # 16k/22k/24k/48k
```

---

## Voice profiles compartilháveis

**O que pode compartilhar (sem risco legal):**
- Voice profile = config YAML (provider + voice_id + tuning)
- NÃO o embedding (não compartilha clone de pessoa real)

```yaml
# Comunidade publica:
# logica-voice-community/voices/cleo-style.yaml
name: cleo-style
description: "Voz feminina criativa pra copywriting/marketing"
provider: kokoro
voice_id: af_bella
speed: 1.05
emphasis: strong
tags: [feminine, creative, copywriting, pt-br]
author: "@usuario"
license: CC0
```

```bash
$ logica voice install cleo-style
✓ Voice profile cleo-style instalado

$ logica voice apply cleo-style --to-agent minhacopy
✓ Agente "minhacopy" agora usa voz cleo-style
```

**Registry público (futuro v0.4):**
- GitHub `logica-voice-community/profiles/`
- ~50-100 profiles curados por comunidade
- 100% CC0/MIT, sem clones de pessoa real

---

## Comandos CLI completos

```bash
# Listar vozes configuradas
logica voice list

# Listar todas as vozes disponíveis (Kokoro pool, etc)
logica voice catalog

# Atribuir voz a agente
logica voice set <agent-slug> --provider kokoro --voice af_bella

# Gravar voz pra agente
logica voice record <agent-slug>

# Importar clone
logica voice import-clone <slug> --source <youtube|file|url> [opts]

# Tocar test
logica voice test <agent-slug> --text "Olá mundo"

# Auto-assign todos os agentes (Tier 1)
logica voice setup-all

# Renomear/remover voz
logica voice remove <agent-slug>
logica voice rename <old-slug> <new-slug>

# Setup completo (Tier 1 auto + perguntas pra Tier 2 + opcional Tier 3)
logica voice setup-wizard

# Export/import voice profiles (sem embeddings)
logica voice export <agent-slug> --output profile.yaml
logica voice apply profile.yaml --to-agent <slug>

# Sharing comunitário (futuro)
logica voice publish <agent-slug>  # publica profile na community registry
logica voice install <profile-name>
```

---

## Ética — princípios de uso

### O sistema é uma faca

Permite tecnicamente:
- ✅ Sua própria voz clonada — uso óbvio, OK
- ✅ Personagem fictício original — OK
- ✅ Clone consensual (cônjuge, sócio, mentor que deu OK) — OK
- ✅ Pessoa pública pra educação/análise — gray, geralmente OK
- ⚠️ Pessoa pública pra comercial — depende de licença/lei local
- ❌ Fingir alguém disse algo falso — **antiético, ilegal em muitos lugares**
- ❌ Deepfake malicioso — crime
- ❌ Fraude (clone de voz pra golpe de banco) — crime grave

### O que Logica Voice faz pra mitigar
1. **Avisos legais explícitos** no CLI antes de clone de pessoa real.
2. **Confirmação obrigatória** ("você confirma uso legítimo?").
3. **Audit log** local de todas as importações (pra defesa em auditoria).
4. **Watermark opcional** (audio watermark imperceptível — opt-in).
5. **Filtros** opt-in pra bloqueio de slugs sensíveis (líderes políticos, figuras controversas).
6. **Documentação clara** dos riscos.

### O que Logica Voice NÃO faz
- ❌ Auto-bloqueia uso "pra prevenir" — usuário é adulto, decide.
- ❌ Coleta dados de uso (sem telemetria silenciosa).
- ❌ Reporta uso pra ninguém.

### Responsabilidade legal
A licença MIT do Logica Voice transfere responsabilidade legal pro usuário. Repo terá NOTICE:

> **Logica Voice** is a voice synthesis framework. It is the user's sole responsibility to ensure that voice cloning of real persons complies with applicable laws and ethical norms. The authors of Logica Voice assume no liability for misuse.

---

## Watermark (audio fingerprint)

**Pra:** uso jornalístico, educacional, profissional onde detectar AI-generated importa.

**Opcional:** opt-in via config:
```yaml
watermark:
  enabled: true
  algorithm: ssm-3       # SilentSeal/AudioSeal família
  payload: "logica-voice-generated"
  detectable_by: ["AudioSeal", "SilentSeal", "compatible"]
```

**Como funciona:**
- TTS gera áudio normal
- Watermarker aplica padrão inaudível (modulação sutil em frequências altas)
- Detectores forenses identificam: "este áudio foi gerado por TTS Logica Voice"
- Detectores comuns: AudioSeal (Meta), SilentSeal, Resemble Detect

**Por que opt-in (não default):**
- Bibliotecas de watermarking adicionam ~50KB ao binário
- Performance: +20-50ms por audio
- Filosofia: usuário decide se quer marca

---

## Filtro de slugs sensíveis (opcional)

Lista comunitária de pessoas que pediram **não serem clonadas** + figuras políticas/controversas:

```yaml
filter:
  enabled: true
  block_list:
    source: "github:logica-voice/sensitive-slugs/main/list.yaml"
    update_interval: monthly
  
  custom_block_list:
    - "minha-ex"           # pessoal
    - "concorrente-x"      # business
```

Se usuário tentar `logica voice import-clone elon-musk`, CLI avisa:
```
⚠️ Slug 'elon-musk' está na lista comunitária de figuras sensíveis.
   Razão: figura pública controversa, alto risco de uso indevido.
   
? Continuar mesmo assim? [y/N]
```

**100% opt-in.** Default: filtro desativado. Usuário ativa se quiser.

---

## Storage e portabilidade

### Onde fica
```
config/
├── voices.yaml                   # configuração principal
└── voices/
    ├── aurora.npy                # embedding Tier 2 (Andre)
    ├── astro.npy
    ├── luna.npy
    └── clones/                   # Tier 3
        ├── steve-jobs.npy
        ├── bourdain.npy
        └── hormozi.npy
```

### Backup
```bash
logica voice backup --output voices-backup.tar.gz
logica voice restore voices-backup.tar.gz
```

### Migração entre máquinas
- Embeddings são `.npy` (NumPy arrays) — portátil entre Linux/Mac/Win
- Copia o diretório `config/voices/` + `voices.yaml`
- Importa: `logica voice setup --from <path>`

### Compartilhamento privado (entre suas máquinas)
- Sync via Dropbox/iCloud/rclone — embeddings cifrados se você ativar
- Multi-tenant LogicaOS: cada workspace tem voices isolados

---

## Benchmarks (latência + qualidade)

| Tier | Voz | First chunk | Tokens/s | Quality | RAM |
|---|---|---:|---:|---:|---:|
| 1 | Kokoro-82M | 80ms | ~150 | 4/5 | 200MB |
| 2 | F5-TTS (clone) | 250ms | ~80 | 5/5 | 2GB |
| 3 | F5-TTS (clone YT) | 250ms | ~80 | 4.5/5 | 2GB |
| (cloud) | ElevenLabs | 200ms | ~100 | 5/5 | $$$ |

**Logica Voice F5-TTS bate ElevenLabs em qualidade + zera o custo.**

---

## Roadmap voice features

### v0.1 — Foundation
- [ ] Tier 1 auto-assign Kokoro
- [ ] Tier 2 record CLI
- [ ] Voice mapping em `voices.yaml`

### v0.2 — Clones
- [ ] Tier 3 import-clone (YouTube/file/url)
- [ ] Avisos legais + confirmação
- [ ] Batch import

### v0.3 — Avançado
- [ ] Per-channel voice
- [ ] Voice overrides ("leia como Bourdain")
- [ ] Watermark opt-in
- [ ] Filtro slugs sensíveis

### v0.4 — Comunidade
- [ ] Voice profiles registry (sem embeddings)
- [ ] `logica voice install <profile>`
- [ ] Templates de agents com vozes recomendadas

### v0.5 — Polish
- [ ] Real-time voice morphing (transição entre 2 vozes)
- [ ] Multi-speaker dialog (Astro + Luna conversando entre si)
- [ ] Sing/whisper modes (Kokoro extended)

---

## TL;DR

**Cada agente, cada clone, cada persona — voz própria, configurável, free.**

3 tiers cobrindo:
- 🥉 Auto (0 trabalho, Kokoro pool)
- 🥈 Record (10-15s mic, F5-TTS clone)
- 🥇 Import (áudio público, F5-TTS clone autêntico)

100% local. 100% open source. Aviso ético firme + ferramentas de mitigação opt-in (watermark, filtros).

Pra Andre: 189 agentes/clones com voz única em ~6h de setup total.
Pra qualquer dev: 1-50 agentes próprios com voz única em minutos.
