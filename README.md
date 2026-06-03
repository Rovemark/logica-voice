# Logica Voice

> **The open-source conversational AI framework — multi-channel, multi-agent, voice-native, 100% local.**
>
> Build voice agents for WhatsApp, Telegram, desktop & web that sound like ElevenLabs, respond in <200ms (Jarvis mode), run on your laptop, and cost **$0/month**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org/)
[![Engine](https://img.shields.io/badge/LVP%20engine-working-brightgreen.svg)](#what-works-today-the-lvp-engine-real-time-voice-pipeline)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Status](https://img.shields.io/badge/status-engine%20alpha-orange.svg)](docs/ROADMAP.md)

```bash
npx create-logica-voice my-bot   # in 30 seconds
```

---

## Why Logica Voice exists

Building a voice agent for WhatsApp + Telegram + desktop today means stitching together:

| You pay | Today | With Logica Voice |
|---|---:|---:|
| ElevenLabs Conversational AI | $99-330/mo | **$0** (Moshi local) |
| ElevenLabs TTS | $22-99/mo | **$0** (F5-TTS / Kokoro local) |
| OpenAI Whisper API | $20-100/mo | **$0** (faster-whisper local) |
| Vapi | $99-499/mo | **$0** (own pipeline) |
| WhatsApp Cloud API | $50-500/mo | **$0** (Baileys) |
| Hosted LLM | $50-1000/mo | **$0-50** (Ollama/MLX local, or BYOK cloud) |
| **Total** | **$340-2500/mo** | **$0-50/mo** |

**One framework, one install, one config file — all channels, all agents, voices that sound human.**

---

## What works today: the **LVP engine** (real-time voice pipeline)

The heart of Logica Voice is **LVP — the Logica Voice Pipeline**: a frame-based,
streaming, full-duplex voice engine written in Python. It's our own take on Pipecat —
same idea (frames flowing through processors), 100% our code, runs 100% local.

```
mic → VAD (Silero) → STT (Whisper) → LLM (yours) → Sentence aggregator → TTS → speaker
                                                          ↑ barge-in (talk over it = it stops)
```

**It's running and stable today.** STT + LLM + TTS stream in parallel — the first
sentence starts speaking before the LLM finishes generating.

### Run it (real, works now)

```bash
# 1. Install the engine (venv + models, ~5-10 min first run)
bash engine/setup.sh

# 2. Start the model servers
source engine/.venv/bin/activate
python engine/servers/whisper_server.py --port 8910 &   # STT
python engine/servers/kokoro_server.py  --port 8911 &   # TTS (fast, ~80MB)

# 3. Start the pipeline — plug ANY LLM that streams SSE
LVP_LLM_URL="http://localhost:11434/v1/chat/completions" \   # e.g. Ollama, OpenAI-compatible
  python engine/live_server.py --port 8915

# 4. Connect over WebSocket (ws://127.0.0.1:8915)
#    send PCM 16kHz int16 mono → receive PCM 24kHz back. Done.
```

The LLM is **pluggable** — point `LVP_LLM_URL` at any SSE endpoint (OpenAI-compatible,
Ollama, your own service, or [LogicaOS](https://logicaos.com)). The engine knows nothing
about your brain — it just streams audio in and out.

> **Heads up:** the `npx create-logica-voice` CLI, the multi-channel YAML config, and the
> TypeScript packages below are the **product vision (roadmap)**. The Python engine above
> is what runs today.

---

## What you get

### 🎙 Voice that doesn't suck

- **Kokoro-82M** (Apache 2.0) — real-time TTS on CPU, ~80MB
- **F5-TTS** (MIT) — voice cloning quality comparable to ElevenLabs from 5-15s of audio
- **Qwen3-TTS** (Apache 2.0) — PT-BR + 9 other languages, streaming
- **Kyutai Moshi** (Apache 2.0 + CC-BY) — full-duplex speech-to-speech, <200ms latency (Jarvis mode)
- **ElevenLabs** as opt-in adapter — if you've already paid, you can still use it

### 📱 Channels built-in

- **WhatsApp** (via [Baileys](https://github.com/WhiskeySockets/Baileys)) — multi-device, free, with proper LID resolution and BR phone normalization
- **Telegram** (Bot API) — long polling with 409 conflict handling
- **Voice desktop** — WebSocket bridge for Mac/Windows native apps
- **Web chat** — React-friendly WebSocket server
- Coming in v0.5: Discord, Slack, iMessage, Email

### 🧠 Multi-agent that actually works

Define your agents in YAML and route by `@mention`:

```yaml
brain:
  provider: built-in
  defaultLlm:
    provider: openai
    model: gpt-4o
  agents:
    - slug: assistant
      systemPrompt: "Você é um assistente útil em PT-BR."
    - slug: copy
      systemPrompt: "Você é uma copywriter de classe mundial."
      voice: kokoro/af_bella
    - slug: dev
      systemPrompt: "Você escreve código limpo."
      voice: kokoro/am_michael
      llm: { provider: ollama, model: qwen3-coder:32b }   # per-agent LLM override
```

Then on WhatsApp:
```
@copy escreva um headline pra meu produto X
@dev refatora essa função pra usar async iterators
```

### 🔌 Brain-agnostic (plug any LLM)

| Adapter | Status | Use case |
|---|---|---|
| `brain-built-in` | ✅ v0.1 | YAML agents + any OpenAI-compatible LLM (OpenAI, Anthropic, Ollama, MLX, Together, Groq, …) |
| `brain-logicaos` | ✅ v0.1 | Plug into [LogicaOS](https://logicaos.com) — get 130+ pre-built agents, squads, chains |
| `brain-openai` | 🚧 v0.2 | Direct OpenAI provider with tool calling |
| `brain-anthropic` | 🚧 v0.2 | Direct Claude with prompt caching |
| `brain-gemini` | 🚧 v0.2 | Google Gemini |
| `brain-ollama` | 🚧 v0.2 | Local Ollama models |
| `brain-mlx` | 🚧 v0.2 | Apple Silicon native MLX models |
| Custom HTTP | ✅ via SSE | Any endpoint that streams SSE chunks |

---

## Architecture

### LVP engine (Python) — what runs today

```
engine/
├── live_server.py          WebSocket server (PCM in → PCM out) + /health
├── lvp/                     the frame pipeline (our "Pipecat")
│   ├── frames.py            AudioInFrame, TranscriptionFrame, LLMTokenFrame,
│   │                        TextSentenceFrame, AudioOutFrame, InterruptionFrame…
│   ├── processor.py         FrameProcessor base + Pipeline runner
│   ├── vad_processor.py     Silero VAD + smart-turn (250ms) + barge-in
│   ├── stt_processor.py     STT over HTTP (any Whisper-compatible server)
│   ├── llm_processor.py     LLM over SSE (OpenAI-compatible OR {token:…})
│   ├── tts_processor.py     SentenceAggregator + TTS (kokoro/pocket/chatterbox)
│   ├── transport.py         frames → WebSocket
│   └── runner.py            wires the pipeline + echo guard
└── servers/                 model HTTP servers (lazy, swappable)
    ├── whisper_server.py    STT  (faster-whisper / mlx-whisper)
    ├── kokoro_server.py     TTS  (Kokoro-82M, fast, ~80MB)
    ├── pocket_tts_server.py TTS  (Kyutai Pocket, PT-BR native)
    └── chatterbox_server.py TTS  (Resemble Chatterbox, voice cloning)
```

**Frames flow downstream** (`VAD → STT → LLM → SentenceAggregator → TTS → Transport`);
`InterruptionFrame` propagates and cancels in-flight work for instant barge-in. Every
backend is an HTTP/SSE endpoint, so you swap STT / LLM / TTS without touching the pipeline.

### Full product (roadmap)

```
┌──────────────────────────────────────────────────────────────┐
│  CHANNELS   WhatsApp · Telegram · Voice desktop · Web         │
├──────────────────────────────────────────────────────────────┤
│  LVP ENGINE (above) — VAD · STT · LLM · TTS · barge-in        │
├──────────────────────────────────────────────────────────────┤
│  BRAIN   built-in (agents.yaml) · LogicaOS · custom HTTP      │
└──────────────────────────────────────────────────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Comparison with alternatives

| Feature | Logica Voice | Pipecat | LiveKit Agents | Vapi | Botpress |
|---|---|---|---|---|---|
| Open source | ✅ MIT | ✅ BSD-2 | ✅ Apache | ❌ SaaS | ✅ MIT |
| Engine language | **Python** (LVP) | Python | Python/Node | SaaS | TypeScript |
| WhatsApp built-in | ✅ | ❌ | ❌ | ❌ | ⚠️ paid |
| Telegram built-in | ✅ | ❌ | ❌ | ❌ | ⚠️ paid |
| Voice desktop | ✅ | ⚠️ DIY | ⚠️ DIY | ✅ | ❌ |
| Multi-agent built-in | ✅ | ❌ | ❌ | ❌ | ⚠️ basic |
| Full-duplex (Jarvis) | ✅ Moshi | ❌ | ❌ | ⚠️ | ❌ |
| Voice cloning OSS | ✅ F5-TTS | ⚠️ plugin | ⚠️ plugin | ❌ paid | ❌ |
| 100% local default | ✅ | ⚠️ | ❌ | ❌ | ⚠️ |
| Minimum monthly cost | **$0** | $0 | $0 | $99-499 | $0 free tier |

We're not "anti-Pipecat" — we're **inspired by it** (see [PIPECAT-COMPARISON.md](docs/PIPECAT-COMPARISON.md)). The LVP engine is our own frame pipeline; what we add on top is built-in channels + multi-agent + voice-per-agent, which is what's missing in the ecosystem.

---

## Voice per agent

Every agent gets its own voice. Three tiers, automatic:

### Tier 1 — Auto-assign (zero setup)
Pool of 10 Kokoro voices (male/female/neutral), auto-mapped by agent gender + personality. Just works.

### Tier 2 — Record your voice
```bash
logica-voice voice record assistant
# Press space to record 10s
# F5-TTS embedding generated → assistant now speaks in your voice
```

### Tier 3 — Import mentor voices
```bash
logica-voice voice import-clone bourdain --source youtube --url <parts-unknown-clip>
# Legal warning shown, confirmation required
# F5-TTS embedding from public audio
```

See [docs/VOICES.md](docs/VOICES.md) for the full voice system + ethics guidelines.

---

## Roadmap

- **v0.1** ✅ — Scaffold, core, brain adapters (built-in + LogicaOS), Telegram, WhatsApp, CLI
- **v0.2** 🚧 — Voice services (faster-whisper, Kokoro, F5-TTS via Python bridge), audio in Telegram/WhatsApp
- **v0.3** — Voice cloning wizard, per-agent voice mapping
- **v0.4** — `npx create-logica-voice`, Docker compose, public release
- **v0.5** — Discord, Slack, WebRTC mobile, LiveKit integration
- **v1.0** — Production hardening, multi-tenant, observability

Full roadmap: [docs/ROADMAP.md](docs/ROADMAP.md)

---

## Packages

```
@logica-voice/core              — frames, pipeline, adapter interfaces
@logica-voice/brain-built-in    — YAML agents + any OpenAI-compatible LLM
@logica-voice/brain-logicaos    — LogicaOS integration (130+ agents)
@logica-voice/brain-{openai,anthropic,gemini,ollama,mlx}  — direct providers (v0.2)
@logica-voice/adapter-telegram  — Telegram Bot API
@logica-voice/adapter-whatsapp  — Baileys (LID-aware, BR phone-normalized, fail-closed ACL)
@logica-voice/adapter-{voice,web}  — desktop/web (v0.2)
@logica-voice/voice-stt         — faster-whisper bridge (v0.2)
@logica-voice/voice-tts         — Kokoro + F5-TTS (v0.2)
@logica-voice/voice-moshi       — Kyutai Moshi full-duplex (v0.2)
@logica-voice/cli               — logica-voice command
```

---

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — Frame-based pipeline, adapter interfaces
- [STACK.md](docs/STACK.md) — Component choices (2026 benchmarks)
- [DECISIONS.md](docs/DECISIONS.md) — Architecture Decision Records
- [VOICE.md](docs/VOICE.md) — Audio pipeline (STT → LLM → TTS, Jarvis mode)
- [VOICES.md](docs/VOICES.md) — Voice-per-agent system (3 tiers + ethics)
- [BRAIN-ADAPTERS.md](docs/BRAIN-ADAPTERS.md) — Plug any LLM
- [LOGICAOS-INTEGRATION.md](docs/LOGICAOS-INTEGRATION.md) — Bundle with LogicaOS for 130+ agents
- [PIPECAT-COMPARISON.md](docs/PIPECAT-COMPARISON.md) — Credit & differences
- [ROADMAP.md](docs/ROADMAP.md) — v0.1 → v1.0

---

## Status

🚧 **v0.1 — scaffold + core + Telegram/WhatsApp adapters.** Voice services and end-to-end Jarvis mode are v0.2.

This is an early release. PRs welcome, no CLA, MIT license forever.

---

## Built with

- TypeScript 5.5+
- Node 20+ (native fetch, async iterators, AbortController)
- pnpm workspaces

## Stands on the shoulders of

- [Pipecat](https://github.com/pipecat-ai/pipecat) — architectural inspiration (frame-based pipeline)
- [Kyutai Moshi](https://github.com/kyutai-labs/moshi) — full-duplex speech foundation model
- [Baileys](https://github.com/WhiskeySockets/Baileys) — WhatsApp Web library
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — tiny, real-time TTS
- [F5-TTS](https://github.com/SWivid/F5-TTS) — zero-shot voice cloning
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — speech-to-text
- [LogicaOS](https://logicaos.com) — first-class brain integration

## License

MIT © [Rovemark](https://github.com/Rovemark) — André Ambrosio

Use it, modify it, sell it. No CLA. No strings.

---

<p align="center">
  <strong>Stop paying ElevenLabs $99/month for what your laptop can do.</strong>
</p>
