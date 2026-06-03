"""
stt_processor.py — Speech-to-Text (genérico, open source).

Recebe UserStoppedSpeakingFrame (WAV) → transcreve → emite TranscriptionFrame.

Backend via HTTP (qualquer servidor STT compatível: {POST /transcribe, multipart
'audio' + 'language', resposta {"text": ...}}). Default aponta pro whisper_server.py
do próprio Logica Voice, mas é trocável por env LVP_STT_URL.

Sem acoplamento a nenhum sistema externo — é só STT.
"""

import os
import aiohttp

from .processor import FrameProcessor, Direction
from .frames import (
    UserStoppedSpeakingFrame, PartialUtteranceFrame, TranscriptionFrame,
    InterimTranscriptionFrame, InterruptionFrame, ErrorFrame,
)

STT_URL = os.environ.get('LVP_STT_URL', 'http://127.0.0.1:8910')
STT_LANG = os.environ.get('LVP_STT_LANG', 'pt')


class STTProcessor(FrameProcessor):
    def __init__(self, url=STT_URL, language=STT_LANG, name=None):
        super().__init__(name)
        self.url = url
        self.language = language

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._cancel_tasks()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, PartialUtteranceFrame):
            # Interim transcription (streaming) — text appears as the user talks.
            self._spawn(self._transcribe(frame.audio_wav, final=False))
            return
        if isinstance(frame, UserStoppedSpeakingFrame):
            self._spawn(self._transcribe(frame.audio_wav, final=True))
            return
        await super().process_frame(frame, direction)

    async def _transcribe(self, wav_bytes, final=True):
        try:
            form = aiohttp.FormData()
            form.add_field('audio', wav_bytes, filename='audio.wav', content_type='audio/wav')
            form.add_field('language', self.language)
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post(f'{self.url}/transcribe', data=form) as r:
                    if r.status != 200:
                        raise RuntimeError(f'STT HTTP {r.status}')
                    data = await r.json()
            text = (data.get('text') or '').strip()
            if text and len(text) >= 2:
                if final:
                    await self.push_frame(TranscriptionFrame(text=text), Direction.DOWNSTREAM)
                else:
                    await self.push_frame(InterimTranscriptionFrame(text=text), Direction.DOWNSTREAM)
        except Exception as e:
            if final:  # interim errors are silent (next partial retries)
                await self.push_frame(ErrorFrame(message=str(e), source=self.name), Direction.DOWNSTREAM)
