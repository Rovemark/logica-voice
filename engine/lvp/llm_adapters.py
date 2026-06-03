"""
llm_adapters.py — direct LLM adapters with native tool calling.

The base LLMProcessor speaks the OpenAI-compatible wire format (works with Ollama,
OpenAI, Groq, Together, vLLM…). These subclasses talk *directly* to providers whose
streaming + tool format differs, converting the universal OpenAI-shaped LLMContext into
each provider's native shape:

  AnthropicLLMProcessor  → POST /v1/messages   (Claude, native tool_use blocks)
  GeminiLLMProcessor     → :streamGenerateContent (Gemini, functionCall parts)

Both reuse the base tool loop in _run() (same (full, tool_calls) contract) — only the
wire format in _stream_llm() changes. Configure with provider keys via env; everything
else (tools, context, frames) is identical to the generic path.

  LVP_ANTHROPIC_KEY / LVP_ANTHROPIC_MODEL
  LVP_GEMINI_KEY    / LVP_GEMINI_MODEL
"""

import os
import json
import aiohttp

from .processor import Direction
from .frames import LLMTokenFrame
from .llm_processor import LLMProcessor


# ─────────────────────────────────────────────────────────────────────
# Anthropic (Claude) — native Messages API + tool_use blocks
# ─────────────────────────────────────────────────────────────────────

class AnthropicLLMProcessor(LLMProcessor):
    def __init__(self, key=None, model=None, max_tokens=1024, **kw):
        super().__init__(**kw)
        self.key = key or os.environ.get('LVP_ANTHROPIC_KEY', '')
        self.model = model or os.environ.get('LVP_ANTHROPIC_MODEL', 'claude-opus-4-8')
        self.max_tokens = max_tokens
        self.api_url = 'https://api.anthropic.com/v1/messages'

    @staticmethod
    def _to_anthropic(messages):
        """OpenAI-shaped messages → (system_str, anthropic_messages)."""
        system = None
        out = []
        for m in messages:
            role = m.get('role')
            if role == 'system':
                system = (system + '\n' if system else '') + (m.get('content') or '')
            elif role == 'user':
                out.append({'role': 'user', 'content': m.get('content') or ''})
            elif role == 'assistant':
                content = []
                if m.get('content'):
                    content.append({'type': 'text', 'text': m['content']})
                for tc in m.get('tool_calls', []) or []:
                    fn = tc.get('function', {})
                    try:
                        args = json.loads(fn.get('arguments') or '{}')
                    except Exception:
                        args = {}
                    content.append({'type': 'tool_use', 'id': tc.get('id'),
                                    'name': fn.get('name'), 'input': args})
                out.append({'role': 'assistant', 'content': content or ''})
            elif role == 'tool':
                out.append({'role': 'user', 'content': [{
                    'type': 'tool_result',
                    'tool_use_id': m.get('tool_call_id'),
                    'content': m.get('content') or '',
                }]})
        return system, out

    @staticmethod
    def _tools_to_anthropic(tools):
        out = []
        for t in tools or []:
            fn = t.get('function', t)
            out.append({
                'name': fn.get('name'),
                'description': fn.get('description', ''),
                'input_schema': fn.get('parameters', {'type': 'object', 'properties': {}}),
            })
        return out

    async def _stream_llm(self, user_text):
        system, messages = self._to_anthropic(self.context.get_messages())
        payload = {
            'model': self.model, 'max_tokens': self.max_tokens,
            'messages': messages, 'stream': True,
        }
        if system:
            payload['system'] = system
        tools = self._tools_to_anthropic(self.context.get_tools())
        if tools:
            payload['tools'] = tools
        headers = {
            'x-api-key': self.key, 'anthropic-version': '2023-06-01',
            'content-type': 'application/json', 'accept': 'text/event-stream',
        }
        full = ''
        tool_calls = []
        cur = None          # tool block being assembled
        cur_args = ''
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(self.api_url, json=payload, headers=headers) as r:
                if r.status != 200:
                    body = await r.text()
                    raise RuntimeError(f'Anthropic HTTP {r.status}: {body[:200]}')
                buf = ''
                async for raw in r.content:
                    buf += raw.decode('utf-8', errors='ignore')
                    while '\n\n' in buf:
                        block, buf = buf.split('\n\n', 1)
                        for line in block.split('\n'):
                            line = line.strip()
                            if not line.startswith('data:'):
                                continue
                            try:
                                evt = json.loads(line[5:].strip())
                            except Exception:
                                continue
                            etype = evt.get('type')
                            if etype == 'content_block_start':
                                cb = evt.get('content_block', {})
                                if cb.get('type') == 'tool_use':
                                    cur = {'id': cb.get('id'), 'name': cb.get('name')}
                                    cur_args = ''
                            elif etype == 'content_block_delta':
                                d = evt.get('delta', {})
                                if d.get('type') == 'text_delta':
                                    tok = d.get('text', '')
                                    if tok:
                                        full += tok
                                        await self.push_frame(LLMTokenFrame(text=tok), Direction.DOWNSTREAM)
                                elif d.get('type') == 'input_json_delta':
                                    cur_args += d.get('partial_json', '')
                            elif etype == 'content_block_stop':
                                if cur is not None:
                                    try:
                                        cur['args'] = json.loads(cur_args or '{}')
                                    except Exception:
                                        cur['args'] = {}
                                    tool_calls.append(cur)
                                    cur = None
                            elif etype == 'message_stop':
                                return full, tool_calls
        return full, tool_calls


# ─────────────────────────────────────────────────────────────────────
# Gemini — streamGenerateContent + functionCall parts
# ─────────────────────────────────────────────────────────────────────

class GeminiLLMProcessor(LLMProcessor):
    def __init__(self, key=None, model=None, **kw):
        super().__init__(**kw)
        self.key = key or os.environ.get('LVP_GEMINI_KEY', '')
        self.model = model or os.environ.get('LVP_GEMINI_MODEL', 'gemini-2.5-flash')

    @staticmethod
    def _to_gemini(messages):
        """OpenAI-shaped messages → (system_instruction, contents)."""
        system = None
        contents = []
        for m in messages:
            role = m.get('role')
            if role == 'system':
                system = (system + '\n' if system else '') + (m.get('content') or '')
            elif role == 'user':
                contents.append({'role': 'user', 'parts': [{'text': m.get('content') or ''}]})
            elif role == 'assistant':
                parts = []
                if m.get('content'):
                    parts.append({'text': m['content']})
                for tc in m.get('tool_calls', []) or []:
                    fn = tc.get('function', {})
                    try:
                        args = json.loads(fn.get('arguments') or '{}')
                    except Exception:
                        args = {}
                    parts.append({'functionCall': {'name': fn.get('name'), 'args': args}})
                contents.append({'role': 'model', 'parts': parts or [{'text': ''}]})
            elif role == 'tool':
                content = m.get('content') or ''
                try:
                    response = json.loads(content)
                    if not isinstance(response, dict):
                        response = {'result': response}
                except Exception:
                    response = {'result': content}
                contents.append({'role': 'user', 'parts': [{'functionResponse': {
                    'name': m.get('name'), 'response': response,
                }}]})
        return system, contents

    @staticmethod
    def _tools_to_gemini(tools):
        decls = []
        for t in tools or []:
            fn = t.get('function', t)
            decls.append({
                'name': fn.get('name'),
                'description': fn.get('description', ''),
                'parameters': fn.get('parameters', {'type': 'object', 'properties': {}}),
            })
        return [{'function_declarations': decls}] if decls else []

    async def _stream_llm(self, user_text):
        system, contents = self._to_gemini(self.context.get_messages())
        url = (f'https://generativelanguage.googleapis.com/v1beta/models/'
               f'{self.model}:streamGenerateContent?alt=sse&key={self.key}')
        payload = {'contents': contents}
        if system:
            payload['systemInstruction'] = {'parts': [{'text': system}]}
        tools = self._tools_to_gemini(self.context.get_tools())
        if tools:
            payload['tools'] = tools
        headers = {'content-type': 'application/json', 'accept': 'text/event-stream'}
        full = ''
        tool_calls = []
        _idx = 0
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(url, json=payload, headers=headers) as r:
                if r.status != 200:
                    body = await r.text()
                    raise RuntimeError(f'Gemini HTTP {r.status}: {body[:200]}')
                buf = ''
                async for raw in r.content:
                    buf += raw.decode('utf-8', errors='ignore')
                    while '\n' in buf:
                        line, buf = buf.split('\n', 1)
                        line = line.strip()
                        if not line.startswith('data:'):
                            continue
                        try:
                            evt = json.loads(line[5:].strip())
                        except Exception:
                            continue
                        for cand in evt.get('candidates', []):
                            for part in cand.get('content', {}).get('parts', []):
                                if 'text' in part and part['text']:
                                    full += part['text']
                                    await self.push_frame(LLMTokenFrame(text=part['text']),
                                                          Direction.DOWNSTREAM)
                                elif 'functionCall' in part:
                                    fc = part['functionCall']
                                    _idx += 1
                                    tool_calls.append({
                                        'id': f"call_{_idx}",
                                        'name': fc.get('name'),
                                        'args': fc.get('args', {}),
                                    })
        return full, tool_calls
