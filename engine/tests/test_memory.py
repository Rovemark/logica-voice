"""LongTermMemory (in-process backend) — retrieval injection + persistence."""

import asyncio

from conftest import run, pipeline, of_type
from lvp.processor import Direction
from lvp.memory import LongTermMemory, InProcessMemoryBackend
from lvp.context import LLMContext
from lvp.frames import TranscriptionFrame, LLMFullResponseFrame


def test_inproc_backend_keyword_overlap():
    b = InProcessMemoryBackend()

    async def go():
        await b.add('user prefers morning meetings', 'u1')
        await b.add('user dislikes spicy food', 'u1')
        return await b.search('when are good meetings?', 'u1', 5)
    hits = run(go())
    assert any('morning meetings' in h for h in hits)
    assert all('spicy' not in h for h in hits)   # no overlap → excluded


def test_memory_injects_into_context():
    ctx = LLMContext(system='base prompt')
    mem = LongTermMemory(ctx, user_id='u1')
    head, _ = pipeline(mem)

    async def go():
        await mem.backend.add('user likes morning meetings', 'u1')
        await head.process_frame(
            TranscriptionFrame(text='good time for meetings?'), Direction.DOWNSTREAM)
    run(go())
    injected = [m for m in ctx.messages if 'Long-term memory' in (m.get('content') or '')]
    assert injected, ctx.messages
    assert ctx.messages[0]['content'] == 'base prompt'   # base system stays first


def test_memory_injection_replaces_not_stacks():
    ctx = LLMContext(system='base')
    mem = LongTermMemory(ctx, user_id='u1')
    head, _ = pipeline(mem)

    async def go():
        await mem.backend.add('fact one about cats', 'u1')
        await head.process_frame(TranscriptionFrame(text='cats?'), Direction.DOWNSTREAM)
        await head.process_frame(TranscriptionFrame(text='cats again?'), Direction.DOWNSTREAM)
    run(go())
    notes = [m for m in ctx.messages if 'Long-term memory' in (m.get('content') or '')]
    assert len(notes) == 1   # replaced, not duplicated


def test_memory_persists_exchange():
    ctx = LLMContext()
    mem = LongTermMemory(ctx, user_id='u1')
    head, _ = pipeline(mem)

    async def go():
        await head.process_frame(TranscriptionFrame(text='my name is Andre'), Direction.DOWNSTREAM)
        await head.process_frame(LLMFullResponseFrame(text='Nice to meet you, Andre'),
                                 Direction.DOWNSTREAM)
        await asyncio.sleep(0.02)   # save task
        return await mem.backend.search('what is my name', 'u1', 5)
    hits = run(go())
    assert any('Andre' in h for h in hits)
