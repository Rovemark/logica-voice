"""
memory.py — long-term memory across sessions (mem0-style).

LLMContext is per-session (forgotten on disconnect). LongTermMemory persists facts about
the user across calls and retrieves the relevant ones at the start of each turn, injecting
them into the system prompt — so the agent remembers "you prefer morning meetings" weeks
later.

Pluggable backend:
  - mem0 (pip install mem0ai) if available and LVP_MEM0=true
  - any HTTP endpoint via LVP_MEMORY_URL (POST {op:'search'|'add', ...})
  - in-process fallback (keyword match) so it works with zero deps for tests

Sits BEFORE the LLM. On TranscriptionFrame it retrieves; after the assistant answers
(LLMFullResponseFrame) it writes the exchange back.
"""

import os
import json
import aiohttp

from .processor import FrameProcessor, Direction
from .frames import TranscriptionFrame, LLMFullResponseFrame, InterruptionFrame

MEMORY_URL = os.environ.get('LVP_MEMORY_URL', '')
USE_MEM0 = os.environ.get('LVP_MEM0', 'false').lower() in ('1', 'true', 'yes')


class LongTermMemory(FrameProcessor):
    """
    Retrieves relevant long-term memories and injects them into the shared LLMContext
    as a system note, then persists each completed exchange.

    Pass the SAME LLMContext instance the LLMProcessor uses so the injected memory note
    is visible to the model.
    """

    def __init__(self, context, user_id='default', top_k=5, backend=None, name=None):
        super().__init__(name)
        self.context = context
        self.user_id = user_id
        self.top_k = top_k
        self.backend = backend or _make_backend()
        self._last_user = None
        self._injected_idx = None

    async def process_frame(self, frame, direction):
        if isinstance(frame, InterruptionFrame):
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TranscriptionFrame):
            self._last_user = frame.text
            try:
                memories = await self.backend.search(frame.text, self.user_id, self.top_k)
            except Exception:
                memories = []
            if memories:
                self._inject(memories)
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, LLMFullResponseFrame):
            if self._last_user:
                exchange = f"User: {self._last_user}\nAssistant: {frame.text}"
                self._spawn(self._save(exchange))
                self._last_user = None
            await self.push_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    def _inject(self, memories):
        note = "[Long-term memory about this user]\n" + "\n".join(f"- {m}" for m in memories)
        msg = {"role": "system", "content": note}
        # replace a prior injection rather than stacking
        if self._injected_idx is not None and self._injected_idx < len(self.context.messages):
            self.context.messages[self._injected_idx] = msg
        else:
            # insert right after the base system prompt (index 1) if present
            insert_at = 1 if (self.context.messages and
                              self.context.messages[0].get('role') == 'system') else 0
            self.context.messages.insert(insert_at, msg)
            self._injected_idx = insert_at

    async def _save(self, exchange):
        try:
            await self.backend.add(exchange, self.user_id)
        except Exception:
            pass


# ─── Backends ────────────────────────────────────────────────────────

def _make_backend():
    if USE_MEM0:
        try:
            return Mem0Backend()
        except Exception:
            pass
    if MEMORY_URL:
        return HTTPMemoryBackend(MEMORY_URL)
    return InProcessMemoryBackend()


class Mem0Backend:
    def __init__(self):
        from mem0 import Memory  # raises if not installed
        self._mem = Memory()

    async def search(self, query, user_id, top_k):
        res = self._mem.search(query=query, user_id=user_id, limit=top_k)
        items = res.get('results', res) if isinstance(res, dict) else res
        return [i.get('memory', str(i)) for i in (items or [])]

    async def add(self, text, user_id):
        self._mem.add(text, user_id=user_id)


class HTTPMemoryBackend:
    def __init__(self, url):
        self.url = url

    async def search(self, query, user_id, top_k):
        async with aiohttp.ClientSession() as s:
            async with s.post(self.url, json={
                'op': 'search', 'query': query, 'user_id': user_id, 'top_k': top_k,
            }) as r:
                data = await r.json()
                return data.get('memories', [])

    async def add(self, text, user_id):
        async with aiohttp.ClientSession() as s:
            await s.post(self.url, json={'op': 'add', 'text': text, 'user_id': user_id})


class InProcessMemoryBackend:
    """Zero-dep keyword-overlap fallback. Good enough for tests/demos, not production."""

    def __init__(self):
        self._store = {}   # user_id -> [text]

    async def search(self, query, user_id, top_k):
        items = self._store.get(user_id, [])
        q = set(query.lower().split())
        scored = [(len(q & set(t.lower().split())), t) for t in items]
        scored = [t for n, t in sorted(scored, key=lambda x: -x[0]) if n > 0]
        return scored[:top_k]

    async def add(self, text, user_id):
        self._store.setdefault(user_id, []).append(text)
