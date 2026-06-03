"""
llm_processor.py — LLM streaming (genérico, open source).

Recebe TranscriptionFrame → chama um endpoint de LLM em streaming → emite
LLMTokenFrame por token e LLMFullResponseFrame no fim.

GENÉRICO: o endpoint é configurável via LVP_LLM_URL. Espera um dos formatos:
  - SSE: linhas "data: {token: '...'}" e "data: {done: true, full: '...'}"
  - OpenAI-compatible: "data: {choices:[{delta:{content:'...'}}]}" + "data: [DONE]"
  - JSON single-shot: {"text": "..."} (fallback, sem streaming)

Mantém histórico curto da conversa pra contexto. Não sabe nada de Astro/tools —
quem integra (LogicaOS) aponta LVP_LLM_URL pro seu backend.
"""

import os
import json
import aiohttp

from .processor import FrameProcessor, Direction
from .frames import (
    TranscriptionFrame, LLMTokenFrame, LLMFullResponseFrame,
    InterruptionFrame, ErrorFrame,
)
from .context import LLMContext

# Default points to a local OpenAI-compatible endpoint (Ollama). Override LVP_LLM_URL
# with your own SSE endpoint — the engine is brain-agnostic.
LLM_URL = os.environ.get('LVP_LLM_URL', 'http://127.0.0.1:11434/v1/chat/completions')
LLM_AGENT = os.environ.get('LVP_LLM_AGENT', 'assistant')
LLM_MODEL = os.environ.get('LVP_LLM_MODEL', '')  # for OpenAI-compatible payloads
LLM_SYSTEM = os.environ.get('LVP_LLM_SYSTEM', '')
MAX_HISTORY = int(os.environ.get('LVP_LLM_MAX_HISTORY', '40'))


class LLMProcessor(FrameProcessor):
    """
    Streams an LLM response per user turn. Conversation lives in an LLMContext
    (multi-turn memory + tool messages). Pass your own context to share it with
    tool-calling (FASE 2.2); otherwise one is created.
    """

    def __init__(self, url=LLM_URL, agent=LLM_AGENT, context=None, name=None):
        super().__init__(name)
        self.url = url
        self.agent = agent
        self.context = context or LLMContext(
            system=LLM_SYSTEM or None, max_messages=MAX_HISTORY,
        )

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            self._cancel_tasks()
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TranscriptionFrame):
            # Repassa pro transport (telemetria stt_final na UI) ANTES de consumir
            await self.push_frame(frame, direction)
            self.context.add_user(frame.text)
            self._spawn(self._run(frame.text))
            return
        await super().process_frame(frame, direction)

    async def _run(self, user_text):
        try:
            full = await self._stream_llm(user_text)
            if full:
                self.context.add_assistant(full)
                await self.push_frame(LLMFullResponseFrame(text=full), Direction.DOWNSTREAM)
        except Exception as e:
            await self.push_frame(ErrorFrame(message=str(e), source=self.name), Direction.DOWNSTREAM)

    async def _stream_llm(self, user_text):
        messages = self.context.get_messages()
        if LLM_MODEL:
            # OpenAI-compatible (Ollama, OpenAI, Together, Groq, vLLM…)
            payload = {
                'model': LLM_MODEL,
                'messages': messages,   # already includes the current user turn
                'stream': True,
            }
            tools = self.context.get_tools()
            if tools:
                payload['tools'] = tools
        else:
            # Generic Logica Voice / custom endpoint: {message, history, agent}
            payload = {
                'message': user_text,
                'history': messages[:-1],   # all but the current user turn
                'agent': self.agent,
            }
        headers = {'Accept': 'text/event-stream', 'Content-Type': 'application/json'}
        full = ''
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(self.url, json=payload, headers=headers) as r:
                if r.status != 200:
                    body = await r.text()
                    raise RuntimeError(f'LLM HTTP {r.status}: {body[:160]}')
                ct = r.headers.get('Content-Type', '')
                if 'event-stream' in ct or 'application/x-ndjson' in ct:
                    buf = ''
                    async for raw in r.content:
                        buf += raw.decode('utf-8', errors='ignore')
                        while '\n\n' in buf:
                            block, buf = buf.split('\n\n', 1)
                            for line in block.split('\n'):
                                line = line.strip()
                                if not line.startswith('data:'):
                                    continue
                                payload_s = line[5:].strip()
                                if payload_s == '[DONE]':
                                    return full
                                try:
                                    evt = json.loads(payload_s)
                                except Exception:
                                    continue
                                tok = self._extract_token(evt)
                                if tok:
                                    full += tok
                                    await self.push_frame(LLMTokenFrame(text=tok), Direction.DOWNSTREAM)
                                if evt.get('done'):
                                    return evt.get('full', full)
                    return full
                else:
                    data = await r.json()
                    full = data.get('text') or data.get('reply') or data.get('content', '')
                    # Sem streaming nativo — emite em pedaços pra downstream começar TTS
                    words = full.split(' ')
                    for i in range(0, len(words), 4):
                        await self.push_frame(LLMTokenFrame(text=' '.join(words[i:i+4]) + ' '),
                                              Direction.DOWNSTREAM)
                    return full

    @staticmethod
    def _extract_token(evt):
        # Formato Logica Voice: {token: '...'}
        if evt.get('token'):
            return evt['token']
        # OpenAI-compatible: {choices:[{delta:{content:'...'}}]}
        try:
            return evt['choices'][0]['delta'].get('content', '')
        except (KeyError, IndexError, TypeError):
            return ''
