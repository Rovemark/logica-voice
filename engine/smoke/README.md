# End-to-end smoke

Proves the whole pipeline works *together* — not just unit-by-unit. It boots the STT
server, the TTS server, a tiny **mock LLM** (so you need no API key), and the live
WebSocket pipeline, then pushes one synthetic spoken turn through it and checks every
stage fired.

```
🎤 synthesized speech  →  VAD  →  STT  →  LLM(mock)  →  TTS  →  🔊 audio back
                          └────────── one real turn, end to end ──────────┘
```

## Run

```bash
# from engine/ (after bash setup.sh)
PYTHON=.venv/bin/python ./smoke/run.sh
# or pick a Whisper size:  WHISPER_MODEL=medium PYTHON=.venv/bin/python ./smoke/run.sh
```

Expected tail:

```
[client] <= stt_final: Oi Astro, tudo bem com você hoje?
[client] <= llm_done:  Oi! Eu ouvi você muito bem. Tudo certo por aqui.
[client] <= metrics:   {'stt_ms': 760, 'llm_ttft_ms': 2, 'tts_ttfb_ms': 1039, 'total_ms': 1802}
CHAIN COMPLETE (VAD→STT→LLM→TTS): ✅ YES
```

Exit code `0` = chain complete. `1` = something broke — check `/tmp/lvp-live.log`; if the
pipeline stalled, the **watchdog** line names the stage it got stuck after.

## Pieces

| File | Role |
|---|---|
| `run.sh` | Boots STT + TTS + mock LLM + live pipeline, runs the client, tears it all down |
| `mock_llm.py` | Stand-in brain — streams a fixed reply over SSE (no API key). Swap with `LVP_LLM_URL` for a real one |
| `smoke_client.py` | Synthesizes input speech, streams it over WS, asserts the chain completed |

To point at a **real** brain instead of the mock, set `LVP_LLM_URL` to your streaming
chat endpoint before launching `live_server.py`.
