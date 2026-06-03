"""
runner.py — monta o pipeline LVP e serve via WebSocket.

Pipeline:
  VAD → STT → LLM → SentenceAggregator → TTS → TransportOutput

O servidor recebe binário (PCM 16k) do cliente e injeta como AudioInFrame na
cabeça do pipeline. Eventos de controle (interrupt/end) viram chamadas no pipeline.

Echo guard: enquanto o bot está falando (+ cauda), descarta áudio de entrada pra
não captar a própria voz (sem AEC de hardware). O barge-in real é detectado pelo
VAD via bot_speaking_getter.

100% genérico — backends (STT/LLM/TTS) configuráveis por env. Sem nada externo.
"""

import os
import json
import time
import asyncio

from .processor import Pipeline, Direction
from .frames import AudioInFrame
from .vad_processor import VADProcessor
from .stt_processor import STTProcessor
from .llm_processor import LLMProcessor
from .tts_processor import SentenceAggregator, TTSProcessor
from .transport import TransportOutput
from .metrics import MetricsCollector
from .rtvi import RTVIObserver

ECHO_TAIL_MS = int(os.environ.get('LVP_ECHO_TAIL_MS', '800'))
SILENCE_GAP_MS = int(os.environ.get('LVP_SILENCE_GAP_MS', '250'))
TTS_ENGINE = os.environ.get('LVP_TTS_ENGINE', 'kokoro')
TTS_URL = os.environ.get('LVP_TTS_URL', 'http://127.0.0.1:8911')
TTS_VOICE = os.environ.get('LVP_TTS_VOICE', 'pm_alex')
# Semantic turn detection: LVP_SMART_TURN=true enables the ML end-of-turn model.
SMART_TURN = os.environ.get('LVP_SMART_TURN', 'false').lower() in ('1', 'true', 'yes')
HARD_STOP_SECS = float(os.environ.get('LVP_HARD_STOP_SECS', '3.0'))
# Latency metrics: on by default (cheap); LVP_METRICS=false to silence.
METRICS = os.environ.get('LVP_METRICS', 'true').lower() in ('1', 'true', 'yes')
# STT streaming partials: emit interim transcriptions every N ms of speech.
# 0 = off (default — runs Whisper once per turn). >0 costs extra STT calls.
PARTIAL_MS = int(os.environ.get('LVP_STT_PARTIAL_MS', '0'))
# RTVI protocol: emit standardized client/server events alongside the native protocol.
RTVI = os.environ.get('LVP_RTVI', 'false').lower() in ('1', 'true', 'yes')


class LVPSession:
    """Uma sessão de voz = um pipeline + estado de echo guard."""

    def __init__(self, ws):
        self.ws = ws
        self._bot_speaking_until = 0.0

        def bot_speaking():
            return time.time() < self._bot_speaking_until

        def on_bot_audio(nbytes):
            # marca "bot falando" pela duração do áudio + cauda de echo
            dur_s = nbytes / 2 / 24000  # int16, 24kHz
            self._bot_speaking_until = max(self._bot_speaking_until, time.time()) + dur_s + ECHO_TAIL_MS / 1000.0

        self.vad = VADProcessor(
            silence_gap_ms=SILENCE_GAP_MS, bot_speaking_getter=bot_speaking,
            smart_turn=SMART_TURN, hard_stop_secs=HARD_STOP_SECS,
            partial_interval_ms=PARTIAL_MS,
        )
        observers = [MetricsCollector(log=True)] if METRICS else []
        self.rtvi = RTVIObserver(ws) if RTVI else None
        if self.rtvi:
            observers.append(self.rtvi)
        self.pipeline = Pipeline([
            self.vad,
            STTProcessor(),
            LLMProcessor(),
            SentenceAggregator(),
            TTSProcessor(url=TTS_URL, voice=TTS_VOICE, engine=TTS_ENGINE),
            TransportOutput(ws, on_bot_audio=on_bot_audio),
        ], observers=observers)

    async def feed_audio(self, pcm: bytes):
        # Echo guard: ignora entrada enquanto bot fala (exceto pra barge-in, que o
        # VAD detecta via bot_speaking_getter ANTES de descartar). Aqui ainda passamos
        # pro VAD pra ele poder detectar barge-in; o VAD é quem decide.
        await self.pipeline.push(AudioInFrame(pcm=pcm), Direction.DOWNSTREAM)

    async def interrupt(self):
        await self.pipeline.interrupt()

    async def end(self):
        await self.pipeline.end()


async def handle_connection(websocket):
    print(f'[lvp] cliente conectado: {websocket.remote_address}', flush=True)
    session = LVPSession(websocket)
    try:
        await websocket.send(json.dumps({
            'type': 'ready', 'sample_rate_in': 16000, 'sample_rate_out': 24000, 'engine': 'lvp',
        }))
        async for message in websocket:
            if isinstance(message, bytes):
                await session.feed_audio(message)
            else:
                try:
                    msg = json.loads(message)
                    if msg.get('type') == 'control':
                        if msg.get('action') == 'interrupt':
                            await session.interrupt()
                        elif msg.get('action') == 'end':
                            await session.end()
                            break
                except Exception:
                    pass
    except Exception as e:
        print(f'[lvp] erro: {e}', flush=True)
    finally:
        try:
            await session.end()
        except Exception:
            pass
        print('[lvp] cliente desconectado', flush=True)


def _health_check(connection, request):
    """Responde GET /health com 200 sem abrir WS — pra probe não virar sessão fantasma."""
    if request.path == '/health':
        return connection.respond(200, '{"ok": true, "engine": "lvp"}\n')
    return None  # segue pro handshake WS normal


async def serve(host='127.0.0.1', port=8915):
    import websockets
    # Pre-warm VAD (baixa modelo Silero na 1a vez)
    print('[lvp] preparando Silero VAD...', flush=True)
    VADProcessor(silence_gap_ms=SILENCE_GAP_MS)
    print(f'[lvp] Logica Voice Pipeline listening on ws://{host}:{port}', flush=True)
    print(f'[lvp] backends: STT={os.environ.get("LVP_STT_URL","8910")} '
          f'LLM={os.environ.get("LVP_LLM_URL","3001")} TTS={TTS_ENGINE}@{TTS_URL}', flush=True)
    async with websockets.serve(handle_connection, host, port, max_size=20_000_000,
                                process_request=_health_check):
        await asyncio.Future()
