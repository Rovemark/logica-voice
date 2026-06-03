# Changelog

All notable changes to Logica Voice will be documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and adhering to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added — LVP engine parity (drivers + advanced processors)
- **Streaming STT** (`streaming_stt`) — WebSocket adapter emitting real interim transcriptions as you speak (vs batch-per-turn).
- **Token-streaming TTS** (`streaming_tts`) — WebSocket adapter pushing audio chunks while text generates.
- **Direct LLM adapters** (`llm_adapters`) — native tool calling for the Messages API (Claude) and `streamGenerateContent` (Gemini); reuses the same agent/tool loop, only the wire format differs.
- **Long-term memory** (`memory`) — `LongTermMemory` persists facts across sessions and injects relevant ones per turn; pluggable backend (mem0 / HTTP / zero-dep in-process).
- **Background audio mixer** (`audio_mixer`) — loops a music/hold bed under the bot's voice, with optional ducking while speaking.
- **Pattern aggregator** (`aggregators`) — strips `<thinking>…</thinking>` (and custom pairs) from the LLM stream so the bot never speaks its scratch-pad.
- **DTMF aggregator** (`aggregators`) — collects phone keypad presses into a turn on a terminator/timeout.
- **Word timestamps** (`aggregators`, `frames`) — `WordTimestampFrame` for karaoke-style word highlighting.
- **Producer/Consumer** (`sync`) — move frames between separate pipelines via a shared queue.
- **Wake word** (`filters`) — `WakeCheckFilter` gates the conversation behind "Astro"/"Jarvis" with a keepalive window; plus generic frame filters.
- **Conversation summarization** (`context`) — compress old turns into a summary instead of dropping them.

### Changed
- **VAD is now a 4-state machine** (`vad_processor`) — QUIET → STARTING → SPEAKING → STOPPING with onset confirmation (`start_secs`, rejects clicks/coughs) and a volume gate (`min_volume`, rejects steady background noise).
- **Lifecycle frames** — `StartFrame` (boot config) and `HeartbeatFrame` (health pulse) propagate through the pipeline; `PauseFrame`/`ResumeFrame` hold/drain data frames while system frames keep flowing; TTS emits `TTSStartedFrame`/`TTSStoppedFrame`.

### Coming in v0.2
- Voice services implementation: faster-whisper, Kokoro, F5-TTS via Python bridge
- Audio in/out in Telegram + WhatsApp adapters
- `npx create-logica-voice` published to npm
- Docker compose for easy deploy
- Vitest test suite

---

## [0.1.0] — 2026-06-02

🎉 **Initial public release** — scaffold + core + Telegram/WhatsApp adapters + CLI.

### Added

**Core framework:**
- `@logica-voice/core` — Frame types (audio_in, audio_out, transcript, llm_messages, llm_response, text, start, end, error, interruption, metrics, control)
- Pipeline runner with frame-based streaming, AbortController support, barge-in helper
- `BaseChannelAdapter` abstract class with dispatch helper, mention detection, BR phone normalization, ACL fail-closed pattern

**Brain adapters:**
- `@logica-voice/brain-built-in` — YAML-based multi-agent config with OpenAI/Anthropic/Ollama/MLX support (any OpenAI-compatible endpoint)
- `@logica-voice/brain-logicaos` — First-class integration with [LogicaOS](https://logicaos.com) Synapses API, exposing 130+ pre-built agents
- Stubs (v0.2): brain-openai, brain-anthropic, brain-gemini, brain-ollama, brain-mlx

**Channel adapters:**
- `@logica-voice/adapter-telegram` — Telegram Bot API via long polling, 409 conflict handling with backoff, ACL fail-closed
- `@logica-voice/adapter-whatsapp` — Baileys with critical fixes preserved:
  - LID resolution via `msg.key.senderPn` / `participantPn` (not just contacts store)
  - BR phone normalization (9th-digit tolerance: 12d ↔ 13d equivalent)
  - Fail-closed ACL (empty allowlist = deny all, not open-world)
  - Auto-reconnect with exponential backoff
  - Graceful logout handling
- Stubs (v0.2): adapter-voice (desktop client), adapter-web (browser)

**Voice services (interfaces ready, implementation v0.2):**
- `@logica-voice/voice-stt` — Interface for faster-whisper / Voxtral / Moonshine
- `@logica-voice/voice-tts` — Interface + `KOKORO_VOICES` pool + `autoAssignKokoroVoice()` heuristic
- `@logica-voice/voice-moshi` — Interface for Kyutai Moshi full-duplex (Jarvis mode)

**CLI:**
- `@logica-voice/cli` — `logica-voice init / start / stop / status / logs / voice / version`
- `init` creates a new project with default `logica-voice.yaml` template
- `start` loads config, instantiates adapters + brain, wires message handlers, runs forever
- Graceful SIGINT shutdown

**Examples:**
- `examples/minimal-telegram-bot/` — Simplest possible bot (Telegram + OpenAI)
- `examples/voice-jarvis/` — Future Moshi full-duplex example

**Project infrastructure:**
- TypeScript 5.5+ strict mode
- pnpm workspaces (16 packages)
- GitHub Actions CI (typecheck on every PR)
- MIT License
- README with badges, comparisons, quick start

### Tested

- ✅ `pnpm install` — 1.2k+ deps installed
- ✅ `pnpm -r build` — 16/16 packages compiled
- ✅ `pnpm -r typecheck` — 16/16 packages green
- ✅ `logica-voice --version / --help / init` — CLI functional end-to-end

### Notes

- **No voice services yet** — Python bridge for STT/TTS/Moshi comes in v0.2
- **WhatsApp/Telegram are text-only in v0.1** — audio/image in v0.2
- **Built-in brain works today** — point at OpenAI/Ollama/MLX and chat works
- **LogicaOS bridge ready** — if you have LogicaOS running on `localhost:3001`, the adapter connects out of the box

### Credits

Inspired by [Pipecat](https://github.com/pipecat-ai/pipecat) (Daily.co). Built on [Baileys](https://github.com/WhiskeySockets/Baileys), [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), [F5-TTS](https://github.com/SWivid/F5-TTS), [Kyutai Moshi](https://github.com/kyutai-labs/moshi), [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

---

[Unreleased]: https://github.com/Rovemark/logica-voice/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Rovemark/logica-voice/releases/tag/v0.1.0
