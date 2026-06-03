# @logica-voice/client

Client SDK for a live **Logica Voice** pipeline. One WebSocket: you stream microphone
audio in, you get transcripts, streaming tokens, and the bot's voice back — with one-call
barge-in. Works in the **browser** and in **Node**.

```bash
npm i @logica-voice/client
```

## Browser (mic + speaker in ~10 lines)

```ts
import { LogicaVoiceClient } from '@logica-voice/client';
import { startMicrophone, createPlayer } from '@logica-voice/client/browser';

const vc = new LogicaVoiceClient('ws://127.0.0.1:8915');
vc.on('sttFinal', t => console.log('you:', t));
vc.on('token',    t => process.stdout.write(t));   // streaming reply text
vc.on('vad', speaking => ui.setListening(speaking));

const player = createPlayer(vc);     // plays the bot's voice, clears on barge-in
await vc.connect();
const mic = await startMicrophone(vc); // streams 16 kHz PCM to the pipeline

// talk over the bot to interrupt it:
button.onclick = () => vc.interrupt();
```

## Node

```ts
import WebSocket from 'ws';
import { LogicaVoiceClient } from '@logica-voice/client';

const vc = new LogicaVoiceClient('ws://127.0.0.1:8915', { WebSocketImpl: WebSocket });
vc.on('audio', pcm => speaker.write(Buffer.from(pcm)));  // PCM 24 kHz int16
await vc.connect();
vc.sendAudio(micPcm16k);   // Int16Array | ArrayBuffer | Uint8Array
```

## React (drop-in hook, ~15 lines)

The core is framework-agnostic — wrap it in a hook for React (same idea for Vue/Svelte):

```tsx
import { useEffect, useRef, useState } from 'react';
import { LogicaVoiceClient } from '@logica-voice/client';
import { startMicrophone, createPlayer } from '@logica-voice/client/browser';

export function useLogicaVoice(url: string) {
  const ref = useRef<LogicaVoiceClient>();
  const [transcript, setTranscript] = useState('');
  const [reply, setReply] = useState('');
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    const vc = new LogicaVoiceClient(url); ref.current = vc;
    vc.on('sttFinal', setTranscript);
    vc.on('token', t => setReply(r => r + t));
    vc.on('vad', setSpeaking);
    createPlayer(vc);                                  // plays the bot's voice
    let mic: { stop(): void } | undefined;
    vc.connect().then(() => startMicrophone(vc)).then(m => { mic = m; });
    return () => { mic?.stop(); vc.close(); };
  }, [url]);

  return { transcript, reply, speaking, interrupt: () => ref.current?.interrupt() };
}
```

## API

`new LogicaVoiceClient(url, { WebSocketImpl? })`

| Method | |
|---|---|
| `connect()` | opens the socket; resolves with the `ready` event |
| `sendAudio(pcm)` | send mic audio — PCM **16 kHz** int16 mono |
| `interrupt()` | barge-in: stop the bot speaking now |
| `end()` | end the session cleanly |
| `close()` | close the socket |
| `on(event, cb)` / `off(event, cb)` | typed listeners |

**Events:** `open` · `ready` · `sttPartial(text)` · `sttFinal(text)` · `token(text)` ·
`response(text)` · `audio(ArrayBuffer)` *(bot voice, PCM 24 kHz)* · `vad(speaking)` ·
`interrupted` · `metrics({...})` · `error(Error)` · `close`.

## The protocol (if you'd rather roll your own)

One WebSocket. **You send:** binary PCM 16 kHz int16 mono (mic), or
`{"type":"control","action":"interrupt"|"end"}`. **You receive:** binary PCM 24 kHz int16
(bot voice), or JSON events (`ready`, `stt_final`, `llm_token`, `llm_done`, `tts_chunk`,
`vad`, `interrupted`, `metrics`, `error`). That's the whole thing — see `protocol.ts`.

MIT.
