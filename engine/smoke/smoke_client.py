"""
End-to-end smoke client for the Logica Voice Pipeline.

1. Synthesize an input phrase via the running Kokoro TTS server, resample to 16 kHz PCM.
2. Connect to the live LVP WebSocket, stream the speech + trailing silence (closes the turn),
   and collect everything that comes back.
3. Assert the WHOLE chain fired: VAD → STT (stt_final) → LLM (llm_done) → TTS (audio back).

This is the one thing unit tests can't prove: that every stage works *together*.
Exit code 0 = chain complete, 1 = something broke (the server's watchdog log will say where).
"""
import asyncio
import io
import json
import os
import sys
import wave
import urllib.request

import numpy as np
import websockets

# self-contained: find the engine root (../) so `import lvp` works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lvp.audio_util import resample_int16   # noqa: E402

WS_URL = os.environ.get('LVP_WS_URL', 'ws://127.0.0.1:8915')
KOKORO = os.environ.get('LVP_TTS_URL', 'http://127.0.0.1:8911') + '/synthesize'
VOICE = os.environ.get('LVP_TTS_VOICE', 'pm_alex')
INPUT_TEXT = os.environ.get('SMOKE_TEXT', 'Oi Astro, tudo bem com você hoje?')


def gen_input_pcm16k(text=INPUT_TEXT):
    body = json.dumps({'text': text, 'voice': VOICE, 'format': 'wav'}).encode()
    req = urllib.request.Request(KOKORO, body, {'Content-Type': 'application/json'})
    wav = urllib.request.urlopen(req, timeout=120).read()
    with wave.open(io.BytesIO(wav), 'rb') as wf:
        sr = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    arr = np.frombuffer(pcm, dtype=np.int16)
    if sr != 16000:
        arr = resample_int16(arr, sr, 16000)
    return arr.tobytes()


async def main():
    print('[client] generating input speech via Kokoro...', flush=True)
    pcm = gen_input_pcm16k()
    print(f'[client] input: {len(pcm)} bytes ({len(pcm)/2/16000:.2f}s of speech)', flush=True)

    events, audio_back = [], 0
    async with websockets.connect(WS_URL, max_size=20_000_000) as ws:
        print('[client] <= ready:', await asyncio.wait_for(ws.recv(), timeout=15), flush=True)

        CH = 1024  # 512 samples = ~32 ms
        for i in range(0, len(pcm), CH):
            await ws.send(pcm[i:i + CH])
            await asyncio.sleep(0.008)
        for _ in range(45):                 # ~1.2 s trailing silence → closes the turn
            await ws.send(b'\x00' * CH)
            await asyncio.sleep(0.008)
        print('[client] sent speech + silence, awaiting response...', flush=True)

        done_at = None
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=20)
            except asyncio.TimeoutError:
                break
            if isinstance(msg, (bytes, bytearray)):
                audio_back += len(msg)
                continue
            ev = json.loads(msg)
            events.append(ev)
            print(f'[client] <= {ev.get("type")}: {ev.get("text") or ev.get("metrics") or ""}', flush=True)
            if ev.get('type') == 'llm_done':
                done_at = asyncio.get_event_loop().time()
            if done_at and audio_back > 0 and asyncio.get_event_loop().time() - done_at > 2.0:
                break

    types = [e['type'] for e in events]
    print('\n===================== SMOKE RESULT =====================', flush=True)
    print('events     :', types, flush=True)
    print('STT heard  :', [e['text'] for e in events if e['type'] == 'stt_final'], flush=True)
    print('audio back :', audio_back, 'bytes', f'({audio_back/2/24000:.2f}s)' if audio_back else '', flush=True)
    ok = ('stt_final' in types) and ('llm_done' in types) and audio_back > 0
    print('CHAIN COMPLETE (VAD→STT→LLM→TTS):', '✅ YES' if ok else '❌ NO', flush=True)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    asyncio.run(main())
