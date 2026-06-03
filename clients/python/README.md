# logica-voice-client (Python)

Async Python client for a live **Logica Voice** pipeline — the same WebSocket protocol as
[`@logica-voice/client`](../../packages/client). Feed it mic PCM, get transcripts,
streaming tokens, and the bot's voice back, with one-call barge-in.

```bash
pip install logica-voice-client
```

```python
import asyncio
from logica_voice import LogicaVoiceClient

async def main():
    vc = LogicaVoiceClient("ws://127.0.0.1:8915")

    @vc.on("stt_final")
    def _(e): print("you said:", e["text"])

    @vc.on("llm_token")            # streaming reply text (one token at a time)
    def _(e): print(e["text"], end="", flush=True)

    @vc.on("audio")
    def _(pcm): play(pcm)          # bot voice — PCM 24 kHz int16 mono

    await vc.connect()             # resolves on the server's `ready`
    await vc.send_audio(mic_pcm)   # PCM 16 kHz int16 mono (bytes)
    await vc.run()                 # process events until the socket closes

asyncio.run(main())
```

## API

`LogicaVoiceClient(url)`

| Method | |
|---|---|
| `await connect()` | open the socket; returns the `ready` event |
| `await send_audio(pcm)` | send mic audio — PCM **16 kHz** int16 mono (bytes) |
| `await interrupt()` | barge-in: stop the bot speaking now |
| `await end()` | end the session cleanly |
| `await run()` | process incoming events until close |
| `await close()` | close the socket |
| `@vc.on(event)` | register a handler (sync or async) |

**Events** (handler gets the event dict, except `audio` which gets raw bytes):
`ready` · `stt_partial` · `stt_final` · `llm_token` · `llm_done` · `tts_chunk` ·
`vad` · `interrupted` · `metrics` · `error` · `audio` · `close`.

The protocol: you send binary PCM 16 kHz (mic) or `{"type":"control","action":...}`;
you receive binary PCM 24 kHz (voice) or JSON events. That's the whole thing.

MIT.
