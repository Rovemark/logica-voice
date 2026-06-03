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

Building a real voice assistant today means renting it, piece by piece, forever —
a meter for speech-to-text, another for the voice, another for the conversation layer,
another for hosting the model. It adds up to **hundreds of dollars a month**, and every
word of every conversation passes through someone else's servers.

A real-time voice agent that sounds great and respects your privacy should cost **$0**
and run on the laptop you already own. That's the whole point.

---

## 🚀 What works today

The heart of Logica Voice is **LVP — the Logica Voice Pipeline**: a frame-based,
streaming, full-duplex voice engine. Audio flows as frames through a chain of small
processors, each doing one job — **100% our code, 100% local.**

```
🎤 you  →  VAD  →  STT  →  LLM  →  sentence aggregator  →  TTS  →  🔊 voice
                          (yours)
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
python engine/servers/whisper_server.py --port 8910 &   # STT
python engine/servers/kokoro_server.py  --port 8911 &   # TTS  (fast, ~80 MB)

# 3. Start the pipeline — plug in ANY LLM that streams (standard chat-completions API)
LVP_LLM_URL="http://localhost:11434/v1/chat/completions" \
LVP_LLM_MODEL="your-model" \
  python engine/live_server.py --port 8915

# 4. Connect over WebSocket (ws://127.0.0.1:8915)
#    send PCM 16 kHz int16 mono  →  receive PCM 24 kHz back. That's the whole protocol.
```

The brain is **yours**. Point `LVP_LLM_URL` at any local model runner, a standard
chat-completions endpoint, your own service, or [LogicaOS](https://logicaos.com). The
engine knows nothing about your intelligence layer — it just streams audio in and voice out.

**Prove it end-to-end** (no API key — uses a mock brain):

```bash
PYTHON=.venv/bin/python ./smoke/run.sh
# → boots STT + TTS + mock LLM + the pipeline, pushes one spoken turn through it,
#   prints  CHAIN COMPLETE (VAD→STT→LLM→TTS): ✅ YES
```

### Talk to it from your app

A full voice UI is a handful of lines with **`@logica-voice/client`** (browser + Node) —
the SDK speaks the same WebSocket protocol, mic and speaker included:

```ts
import { LogicaVoiceClient } from '@logica-voice/client';
import { startMicrophone, createPlayer } from '@logica-voice/client/browser';

const vc = new LogicaVoiceClient('ws://127.0.0.1:8915');
vc.on('sttFinal', t => console.log('you:', t));   // what you said
vc.on('token',    t => render(t));                 // streaming reply text
createPlayer(vc);                                  // plays the bot's voice (gapless)
await vc.connect();
await startMicrophone(vc);                          // stream mic → pipeline
// talk over it to interrupt:  vc.interrupt()
```

Typed events (`sttFinal` · `token` · `response` · `audio` · `vad` · `interrupted` ·
`metrics`), one-call barge-in, no framework. See [`packages/client`](packages/client).

**Python too** — same protocol, async:

```python
from logica_voice import LogicaVoiceClient          # pip install logica-voice-client
vc = LogicaVoiceClient("ws://127.0.0.1:8915")
@vc.on("stt_final")
def _(e): print("you:", e["text"])
await vc.connect(); await vc.send_audio(mic_pcm); await vc.run()
```

See [`clients/python`](clients/python). **React/Vue/Svelte:** the client is
framework-agnostic — drop it into your lifecycle (a `useLogicaVoice` hook is ~10 lines).
**Native iOS/Android:** on the roadmap; the protocol is small enough to implement directly.

---

## 🧩 Architecture

```
engine/
├── live_server.py          WebSocket server (PCM in → voice out) + /health
├── lvp/                     the frame pipeline
│   ├── frames.py            AudioInFrame · TranscriptionFrame · LLMTokenFrame
│   │                        TextSentenceFrame · AudioOutFrame · InterruptionFrame …
│   ├── processor.py         FrameProcessor base + Pipeline runner
│   ├── vad_processor.py     VAD · 4-state machine · smart-turn (250 ms) · barge-in
│   ├── stt_processor.py     speech-to-text  (any compatible HTTP server)
│   ├── streaming_stt.py     WebSocket streaming STT (interim text as you talk)
│   ├── llm_processor.py     LLM over SSE    (standard chat-completions OR {token:…})
│   ├── llm_adapters.py      direct LLM adapters with native tool calling
│   ├── tts_processor.py     sentence aggregator + text-to-speech
│   ├── streaming_tts.py     WebSocket token-streaming TTS
│   ├── context.py           multi-turn memory + conversation summarization
│   ├── context_aggregator.py fuse fragmented turns → clean LLMContext
│   ├── filters.py           wake word · STT-mute · gated · frame gates
│   ├── aggregators.py       hide <thinking> · DTMF→turn · word timestamps
│   ├── interruptions.py     barge-in strategies (min duration / min words)
│   ├── transcript.py        structured running transcript + events
│   ├── params.py            PipelineParams — global switches
│   ├── watchdog.py          stalled-pipeline detection (heartbeat round-trip)
│   ├── audio_mixer.py       background music / hold bed
│   ├── memory.py            long-term memory across sessions
│   ├── sync.py              Producer/Consumer — frames across pipelines
│   ├── serializers.py       JSON · Msgpack · Protobuf
│   ├── telephony.py         Twilio · Telnyx · Plivo · Exotel + DTMF
│   ├── transport.py         frames → WebSocket
│   └── runner.py            wires the pipeline + echo guard
└── servers/                 swappable model servers — pick your trade-off
    ├── whisper_server.py    STT  · fast, accurate, Apple-Silicon aware
    ├── kokoro_server.py     TTS  · tiny & instant (~80 MB), multilingual
    ├── pocket_tts_server.py TTS  · PT-BR native, CPU-only
    └── chatterbox_server.py TTS  · top-tier quality + voice cloning
```
*(server file names reflect the open models they run; each is swappable.)*

Frames flow downstream (`VAD → STT → LLM → aggregate → TTS → out`). An
`InterruptionFrame` propagates and cancels in-flight work for **instant barge-in**.
Every backend is an HTTP/SSE endpoint — swap STT, LLM or TTS **without touching the
pipeline.** That's the whole philosophy: small parts, clean seams, your choice at every layer.

### Everything the engine does

| Capability | Module |
|---|---|
| 🎯 Semantic turn detection (knows you're not done talking, PT-BR) | `smart_turn` |
| 🎚️ VAD state machine (4-state · onset confirm · volume gate) | `vad_processor` |
| ⚡ Streaming STT — batch partials or full WebSocket interim | `stt_processor`, `streaming_stt` |
| 🧠 Multi-turn memory + conversation summarization | `context` |
| ♾️ Long-term memory across sessions (pluggable backend) | `memory` |
| 🛠️ Function/tool calling (LLM → tool → LLM agent loop) | `tools` |
| 🔗 Direct LLM adapters with native tool calling | `llm_adapters` |
| 🗣️ Token-streaming TTS (audio while it generates) | `streaming_tts` |
| 💬 Wake word ("Astro"/"Jarvis", configurable) | `filters` |
| 🙊 STT-mute while the bot speaks / runs a tool | `filters` |
| 🧩 Turn aggregation — fuse fragmented STT into clean turns | `context_aggregator` |
| 🤫 Hide `<thinking>` blocks from speech | `aggregators` |
| 🛑 Barge-in strategies (min speech duration / min words) | `interruptions` |
| 🎛️ PipelineParams — global switches (`allow_interruptions`…) | `params` |
| ⏯️ Pause/resume + lifecycle frames (Start · Heartbeat) | `processor`, `frames` |
| ✂️ Barge-in + priority frames (system frames never queue) | `processor`, `frames` |
| 🐕 Watchdog — pinpoints the stalled stage | `watchdog` |
| 🧾 Structured running transcript (+ update events) | `transcript` |
| 📊 Latency metrics (TTFB per stage) | `metrics` |
| 🔭 OpenTelemetry tracing (optional) | `tracing` |
| 🎙️ Conversation recording (stereo user/bot WAV) | `recording` |
| 🎵 Background audio mixer (music / hold bed) | `audio_mixer` |
| 🔇 Noise suppression (before VAD/STT) | `audio_filter` |
| ⏰ User idle / re-engagement | `idle_processor` |
| 🔌 RTVI protocol (standard client SDKs) | `rtvi` |
| 📦 JSON / Msgpack / Protobuf serializers | `serializers` |
| 🚧 Gated processor (hold frames until a gate opens) | `filters` |
| 🌐 WebSocket + WebRTC transports | `transports` |
| ☎️ Telephony — Twilio · Telnyx · Plivo · Exotel + DTMF→turn | `telephony`, `aggregators` |
| ⏱️ Word timestamps (karaoke-style highlight) | `aggregators`, `frames` |
| 👁️ Vision/multimodal frames | `frames` |
| 🔀 ParallelPipeline · service failover · Producer/Consumer | `advanced`, `sync` |

Everything a serious voice agent needs — **100% ours, all local, MIT.**

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
- **🔌 Brain-agnostic** — any local or cloud LLM, or [LogicaOS](https://logicaos.com)'s
  agent fleet. Bring your own intelligence.

We're building it in the open, piece by piece — and the most important piece, the
real-time voice engine, **already works.**

---

## ✨ What sets it apart

- **Local by default** — no cloud, no API keys, no meter. Your conversations stay on your machine.
- **Full-duplex + barge-in** — talk over it and it stops, like a real conversation.
- **Streaming everywhere** — it starts speaking the first sentence before it finishes thinking.
- **Voice cloning, open** — give any agent a custom voice from a short sample.
- **Brain-agnostic** — bring any LLM; swap any STT/TTS without touching the pipeline.
- **Channels + multi-agent** (vision) — one brain, every surface, each agent its own voice.
- **$0/month** — it runs on the laptop you already own.

---

## 🗺️ Roadmap

- **Engine (alpha)** ✅ — LVP pipeline · VAD state-machine · smart-turn · STT (+streaming) ·
  LLM (SSE + direct adapters w/ tools) · TTS (+token-streaming) · barge-in · long-term memory ·
  wake word · mixer · telephony · WebRTC
- **Client SDKs (alpha)** ✅ — `@logica-voice/client` (browser + Node) and
  `logica-voice-client` (Python). React/Vue/Svelte via the framework-agnostic core; native
  mobile next.
- **End-to-end smoke** ✅ — one command boots the whole stack and proves a real turn
- **Voice depth** 🚧 — voice cloning wizard, per-agent voice mapping, emotion control
- **Channels** — WhatsApp · Telegram · desktop · web adapters on top of the engine
- **Multi-agent** — YAML agents, `@mention` routing, per-agent LLM + voice
- **One-command install** — `npx create-logica-voice`, Docker compose, public release
- **Jarvis** — lower-latency turn, <1 s voice-to-voice end to end

---

## 🙏 Built on open source

Logica Voice stands on a foundation of excellent open models and libraries — for voice
activity detection, speech-to-text, and text-to-speech. Each model server is swappable,
so you choose the licenses and trade-offs that fit your project. Attribution and license
notes live alongside each server in `engine/servers/`.

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
