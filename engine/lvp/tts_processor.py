"""
tts_processor.py — SentenceAggregator + TTS (genérico, open source).

SentenceAggregator: recebe LLMTokenFrame (stream), acumula, e emite TextSentenceFrame
assim que uma sentença fecha (. ! ? \n). É o que permite o TTS começar a falar a
PRIMEIRA frase enquanto o LLM ainda gera o resto → latência percebida despenca.

TTSProcessor: recebe TextSentenceFrame → sintetiza → emite AudioOutFrame.
Backend HTTP configurável (LVP_TTS_URL). Sintetiza em ordem (fila) pra áudio contíguo.

Ambos genéricos — sem nada de sistema externo.
"""

import os
import re
import io
import wave
import asyncio
import aiohttp

from .processor import FrameProcessor, Direction
from .frames import (
    LLMTokenFrame, LLMFullResponseFrame, TextSentenceFrame, AudioOutFrame,
    TTSStartedFrame, TTSStoppedFrame, InterruptionFrame, ErrorFrame,
)

TTS_URL = os.environ.get('LVP_TTS_URL', 'http://127.0.0.1:8911')   # kokoro default (rápido)
TTS_VOICE = os.environ.get('LVP_TTS_VOICE', 'pm_alex')
TTS_ENGINE = os.environ.get('LVP_TTS_ENGINE', 'kokoro')            # kokoro | pocket | chatterbox
SAMPLE_RATE_OUT = 24000

# ─── Limpeza de texto pra fala (remove markdown/box/emoji) ──────────

def clean_for_tts(text: str) -> str:
    lines = []
    for line in text.split('\n'):
        t = line.strip()
        if not t:
            lines.append(line); continue
        if re.fullmatch(r'[╔═╗║╚╝╠╣┌─┐└│◇▶↳·┼\s]+', t):
            continue
        if t.startswith('║') or t.endswith('║'):
            inner = re.sub(r'[╔═╗║╚╝╠╣┌─┐└│]', '', t).strip()
            if inner: lines.append(inner)
            continue
        if re.match(r'^[┌└◇▶]', t) or t.startswith('──'):
            continue
        lines.append(line)
    text = '\n'.join(lines)
    text = re.sub(r'[╔═╗║╚╝╠╣┌─┐└│◇▶↳╟╦╩╬]', '', text)
    text = re.sub(r'[*_`~#]', '', text)
    text = re.sub(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF]', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'^[-*•]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Quebra incremental: dado o buffer acumulado, retorna (sentenças_completas, resto)
_SENT_RE = re.compile(r'(.+?[.!?…])(\s+|$)', re.DOTALL)

def extract_sentences(buf: str):
    sents = []
    pos = 0
    for m in _SENT_RE.finditer(buf):
        s = m.group(1).strip()
        if s:
            sents.append(s)
        pos = m.end()
    return sents, buf[pos:]


class SentenceAggregator(FrameProcessor):
    """Acumula tokens do LLM e emite sentenças completas pro TTS na hora."""

    def __init__(self, min_len=2, name=None):
        super().__init__(name)
        self._buf = ''
        self._min_len = min_len

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._buf = ''
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, LLMTokenFrame):
            self._buf += frame.text
            cleaned = clean_for_tts(self._buf)
            sents, rest = extract_sentences(cleaned)
            if sents:
                # emite todas as sentenças fechadas; mantém o resto incompleto
                for s in sents:
                    if len(s) > self._min_len:
                        await self.push_frame(TextSentenceFrame(text=s), Direction.DOWNSTREAM)
                self._buf = rest
            return
        if isinstance(frame, LLMFullResponseFrame):
            # flush do que sobrou
            leftover = clean_for_tts(self._buf).strip()
            if len(leftover) > self._min_len:
                await self.push_frame(TextSentenceFrame(text=leftover), Direction.DOWNSTREAM)
            self._buf = ''
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)


class TTSProcessor(FrameProcessor):
    """Sintetiza TextSentenceFrame → AudioOutFrame, em ordem (fila serial)."""

    def __init__(self, url=TTS_URL, voice=TTS_VOICE, engine=TTS_ENGINE,
                 voice_prompt_path=None, name=None):
        super().__init__(name)
        self.url = url
        self.voice = voice
        self.engine = engine
        self.voice_prompt_path = voice_prompt_path or os.environ.get('LVP_VOICE_PROMPT_PATH')
        self._queue = asyncio.Queue()
        self._worker = None

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            # Esvazia a fila — para de falar imediatamente (barge-in)
            self._drain_queue()
            self._cancel_tasks()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TextSentenceFrame):
            if self._worker is None or self._worker.done():
                self._worker = self._spawn(self._run_worker())
            await self._queue.put(frame.text)
            return
        await super().process_frame(frame, direction)

    def _drain_queue(self):
        try:
            while True:
                self._queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    async def _run_worker(self):
        self._speaking = False
        while True:
            try:
                # Wait for the next sentence; if the queue drains, mark TTS stopped.
                try:
                    text = await asyncio.wait_for(self._queue.get(), timeout=0.3)
                except asyncio.TimeoutError:
                    if self._speaking:
                        self._speaking = False
                        await self.push_frame(TTSStoppedFrame(), Direction.DOWNSTREAM)
                    continue
                if not self._speaking:
                    self._speaking = True
                    await self.push_frame(TTSStartedFrame(), Direction.DOWNSTREAM)
                wav = await self._synthesize(text)
                pcm = self._wav_to_pcm(wav)
                await self.push_frame(AudioOutFrame(pcm=pcm, text=text), Direction.DOWNSTREAM)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await self.push_frame(ErrorFrame(message=f'TTS: {e}', source=self.name),
                                      Direction.DOWNSTREAM)

    async def _synthesize(self, text):
        if self.engine == 'chatterbox':
            payload = {
                'text': text, 'lang': 'pt',
                'exaggeration': float(os.environ.get('LV_CHATTERBOX_EXAGGERATION', '0.4')),
                'cfg_weight': float(os.environ.get('LV_CHATTERBOX_CFG_WEIGHT', '0.55')),
                'temperature': float(os.environ.get('LV_CHATTERBOX_TEMPERATURE', '0.6')),
            }
            if self.voice_prompt_path and os.path.exists(self.voice_prompt_path):
                payload['audio_prompt_path'] = self.voice_prompt_path
        elif self.engine == 'pocket':
            payload = {'text': text, 'voice': self.voice or 'rafael', 'lang': 'portuguese'}
        else:  # kokoro
            payload = {'text': text, 'voice': self.voice or 'pm_alex', 'format': 'wav'}

        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(f'{self.url}/synthesize', json=payload) as r:
                if r.status != 200:
                    raise RuntimeError(f'TTS HTTP {r.status}')
                return await r.read()

    @staticmethod
    def _wav_to_pcm(wav_bytes):
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            sr = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())
        if sr == SAMPLE_RATE_OUT:
            return pcm
        import numpy as np
        from .audio_util import resample_int16
        src = np.frombuffer(pcm, dtype=np.int16)
        return resample_int16(src, sr, SAMPLE_RATE_OUT).tobytes()
