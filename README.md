<div align="center">

# 🎙️ Logica Voice

### Give every AI a voice. Run it on your laptop. Pay nothing.

**The open-source, voice-native conversational AI engine — full-duplex, multi-agent, 100% local.**
*Your Jarvis. Your voice. Your machine. Your rules.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org/)
[![Engine](https://img.shields.io/badge/LVP%20engine-working-brightgreen.svg)](#-what-works-today)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Status](https://img.shields.io/badge/status-engine%20alpha-orange.svg)](#-roadmap)

</div>

---

## The dream

You talk. It answers — in a real voice, instantly, naturally. You cut it off mid-sentence
and it stops, like a human would. It runs **entirely on your machine** — no cloud, no
API keys, no per-minute meter ticking, no company reading your conversations.

Every agent has **its own voice**. Your copywriter sounds different from your developer.
You can even **clone your own voice** from 10 seconds of audio and let your assistant
speak as you.

That's the dream. **The engine that makes it real is already here.**

---

## 💸 Why Logica Voice exists

Building a real voice assistant today means renting it, piece by piece, forever:

| You'd pay for | Typical cost | With Logica Voice |
|---|---:|---:|
| ElevenLabs Conversational AI | $99–330/mo | **$0** |
| ElevenLabs / cloud TTS | $22–99/mo | **$0** |
| Whisper / cloud STT | $20–100/mo | **$0** |
| Vapi / hosted voice agent | $99–499/mo | **$0** |
| Hosted LLM | $50–1000/mo | **$0–50** (local, or your own key) |

A real-time voice agent that sounds great and respects your privacy should not cost
hundreds of dollars a month. It should run on the laptop you already own.

---

## 🚀 What works today

The heart of Logica Voice is **LVP — the Logica Voice Pipeline**: a frame-based,
streaming, full-duplex voice engine. It's our own take on [Pipecat](https://github.com/pipecat-ai/pipecat) —
same beautiful idea (frames flowing through processors), **100% our code, 100% local.**

```
🎤 you  →  VAD  →  STT  →  LLM  →  sentence aggregator  →  TTS  →  🔊 voice
              (Silero)  (Whisper)  (yours)                  (Kokoro/…)
                  ↑__________________ barge-in __________________↑
              talk over it → it stops, instantly
```

**It runs and it's stable.** STT, LLM and TTS stream in parallel — the **first sentence
starts speaking before the LLM has even finished thinking.** That's the trick to feeling
real-time without a cloud doing the heavy lifting.

### Run it (for real, right now)

```bash
# 1. Install the engine (venv + models — ~5-10 min first run)
bash engine/setup.sh

# 2. Start the model servers
source engine/.venv/bin/activate
python engine/servers/whisper_server.py --port 8910 &   # STT  (faster-whisper / MLX)
python engine/servers/kokoro_server.py  --port 8911 &   # TTS  (Kokoro-82M, ~80 MB)

# 3. Start the pipeline — plug in ANY LLM that streams
LVP_LLM_URL="http://localhost:11434/v1/chat/completions" \
LVP_LLM_MODEL="llama3.2" \
  python engine/live_server.py --port 8915

# 4. Connect over WebSocket (ws://127.0.0.1:8915)
#    send PCM 16 kHz int16 mono  →  receive PCM 24 kHz back. That's the whole protocol.
```

The brain is **yours**. Point `LVP_LLM_URL` at Ollama, an OpenAI-compatible endpoint,
your own service, or [LogicaOS](https://logicaos.com). The engine knows nothing about
your intelligence layer — it just streams audio in and voice out.

---

## 🧩 Architecture

```
engine/
├── live_server.py          WebSocket server (PCM in → voice out) + /health
├── lvp/                     the frame pipeline — our "Pipecat"
│   ├── frames.py            AudioInFrame · TranscriptionFrame · LLMTokenFrame
│   │                        TextSentenceFrame · AudioOutFrame · InterruptionFrame …
│   ├── processor.py         FrameProcessor base + Pipeline runner
│   ├── vad_processor.py     Silero VAD · smart-turn (250 ms) · barge-in
│   ├── stt_processor.py     speech-to-text  (any Whisper-compatible HTTP server)
│   ├── llm_processor.py     LLM over SSE    (OpenAI-compatible OR {token:…})
│   ├── tts_processor.py     sentence aggregator + TTS (kokoro/pocket/chatterbox)
│   ├── transport.py         frames → WebSocket
│   └── runner.py            wires the pipeline + echo guard
└── servers/                 swappable model servers — pick your trade-off
    ├── whisper_server.py    STT  · faster-whisper / mlx-whisper
    ├── kokoro_server.py     TTS  · Kokoro-82M — fast, tiny, multilingual
    ├── pocket_tts_server.py TTS  · Kyutai Pocket — PT-BR native, CPU-only
    └── chatterbox_server.py TTS  · Resemble Chatterbox — #1 TTS Arena, voice cloning
```

Frames flow downstream (`VAD → STT → LLM → aggregate → TTS → out`). An
`InterruptionFrame` propagates and cancels in-flight work for **instant barge-in**.
Every backend is an HTTP/SSE endpoint — swap STT, LLM or TTS **without touching the
pipeline.** That's the whole philosophy: small parts, clean seams, your choice at every layer.

---

## 🎨 The full vision

The engine is the foundation. On top of it, Logica Voice grows into a complete
conversational platform:

- **📱 Channels everywhere** — WhatsApp, Telegram, desktop, web. One brain, every surface.
- **🧠 Multi-agent** — define agents in YAML, route by `@mention`. Your copywriter,
  your dev, your support agent — each with its own personality and **its own voice.**
- **🗣️ Voice per agent** — a pool of ready voices, or **clone your own** from a short
  sample, or craft a custom one. Every persona sounds coherent and distinct.
- **⚡ Jarvis mode** — true full-duplex, sub-second, all local.
- **🔌 Brain-agnostic** — OpenAI, Anthropic, Gemini, Ollama, MLX, or [LogicaOS](https://logicaos.com)'s
  agent fleet. Bring your own intelligence.

We're building it in the open, piece by piece — and the most important piece, the
real-time voice engine, **already works.**

---

## ⚖️ How we compare

| | Logica Voice | Pipecat | LiveKit Agents | Vapi | ElevenLabs |
|---|---|---|---|---|---|
| Open source | ✅ MIT | ✅ BSD-2 | ✅ Apache | ❌ SaaS | ❌ SaaS |
| 100% local default | ✅ | ⚠️ | ❌ | ❌ | ❌ |
| Full-duplex + barge-in | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Voice cloning (OSS) | ✅ Chatterbox | ⚠️ plugin | ⚠️ plugin | ❌ paid | ✅ paid |
| Channels built-in (vision) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Multi-agent built-in (vision) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Minimum monthly cost | **$0** | $0 | $0 | $99–499 | $22–330 |

We're not anti-Pipecat — we're **inspired by it.** LVP is our own frame pipeline; what
we add is built-in channels, multi-agent, and voice-per-agent — the parts the ecosystem
is still missing.

---

## 🗺️ Roadmap

- **Engine (alpha)** ✅ — LVP frame pipeline · VAD · STT · LLM(SSE) · TTS · barge-in · streaming
- **Voice depth** 🚧 — Chatterbox voice cloning wizard, per-agent voice mapping, emotion control
- **Channels** — WhatsApp · Telegram · desktop · web adapters on top of the engine
- **Multi-agent** — YAML agents, `@mention` routing, per-agent LLM + voice
- **One-command install** — `npx create-logica-voice`, Docker compose, public release
- **Jarvis** — lower-latency turn, streaming STT (partials), <1 s voice-to-voice

---

## 🙏 Stands on the shoulders of

- [Pipecat](https://github.com/pipecat-ai/pipecat) — the frame-pipeline idea that inspired LVP
- [Silero VAD](https://github.com/snakers4/silero-vad) — voice activity detection
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [mlx-whisper](https://github.com/ml-explore/mlx-examples) — speech-to-text
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — tiny, real-time TTS
- [Kyutai Pocket TTS](https://kyutai.org/) — PT-BR native streaming TTS
- [Resemble Chatterbox](https://github.com/resemble-ai/chatterbox) — top-tier TTS + voice cloning

---

## 🤝 Contributing

Early days, big dreams. PRs welcome — **no CLA, MIT forever.** Start with the engine
(`engine/lvp/`), add a TTS server, wire a new channel, or improve latency. Open an
issue, tell us what you're building.

## License

**MIT** © [Rovemark](https://github.com/Rovemark) — André Ambrosio.
Use it, fork it, ship it, sell it. No strings.

---

<div align="center">

**Stop renting your assistant's voice. Own it.**

*Built for everyone who believes great AI shouldn't cost $99 a month — and shouldn't
phone home.*

</div>
