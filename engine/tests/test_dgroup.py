"""Group D: STTMuteFilter, context aggregators, TranscriptProcessor, PipelineParams."""

import asyncio

from conftest import run, pipeline, feed, of_type
from lvp.processor import Direction
from lvp.filters import STTMuteFilter, STTMuteStrategy
from lvp.context_aggregator import UserContextAggregator, AssistantContextAggregator
from lvp.context import LLMContext
from lvp.transcript import TranscriptProcessor
from lvp.params import PipelineParams
from lvp.frames import (
    AudioInFrame, TTSStartedFrame, TTSStoppedFrame, FunctionCallFrame,
    FunctionCallResultFrame, TranscriptionFrame, LLMTokenFrame, LLMFullResponseFrame,
    InterruptionFrame, TranscriptionUpdateFrame,
)


# ─── D1 STTMuteFilter ────────────────────────────────────────────────

def _audio_texts(sink):
    return [f.pcm for f in of_type(sink.out, AudioInFrame)]


def test_mute_always_while_bot_speaks():
    head, sink = pipeline(STTMuteFilter(strategies=(STTMuteStrategy.ALWAYS_WHILE_BOT_SPEAKS,)))
    run(feed(head, [
        TTSStartedFrame(), AudioInFrame(pcm=b'x'),   # dropped (bot speaking)
        TTSStoppedFrame(), AudioInFrame(pcm=b'y'),   # passes
    ]))
    assert _audio_texts(sink) == [b'y']


def test_mute_until_first_bot_complete():
    head, sink = pipeline(STTMuteFilter(strategies=(STTMuteStrategy.UNTIL_FIRST_BOT_COMPLETE,)))
    run(feed(head, [
        AudioInFrame(pcm=b'a'),                       # dropped (no bot turn yet)
        TTSStartedFrame(), AudioInFrame(pcm=b'b'),    # dropped
        TTSStoppedFrame(), AudioInFrame(pcm=b'c'),    # passes (first bot turn done)
    ]))
    assert _audio_texts(sink) == [b'c']


def test_mute_function_call():
    head, sink = pipeline(STTMuteFilter(strategies=(STTMuteStrategy.FUNCTION_CALL,)))
    run(feed(head, [
        AudioInFrame(pcm=b'a'),                                 # passes
        FunctionCallFrame(name='t'), AudioInFrame(pcm=b'b'),    # dropped (tool running)
        FunctionCallResultFrame(name='t'), AudioInFrame(pcm=b'c'),  # passes
    ]))
    assert _audio_texts(sink) == [b'a', b'c']


def test_mute_custom_callback():
    flag = {'on': True}
    head, sink = pipeline(STTMuteFilter(
        strategies=(STTMuteStrategy.CUSTOM,), should_mute=lambda: flag['on']))
    run(feed(head, [AudioInFrame(pcm=b'a')]))
    assert _audio_texts(sink) == []
    flag['on'] = False
    run(feed(head, [AudioInFrame(pcm=b'b')]))
    assert _audio_texts(sink) == [b'b']


# ─── D2 Context aggregators ──────────────────────────────────────────

def test_user_aggregator_passthrough_when_no_timeout():
    ctx = LLMContext()
    head, sink = pipeline(UserContextAggregator(context=ctx, aggregation_timeout=0))
    run(feed(head, [TranscriptionFrame(text='oi astro')]))
    assert [f.text for f in of_type(sink.out, TranscriptionFrame)] == ['oi astro']
    assert ctx.messages[-1] == {'role': 'user', 'content': 'oi astro'}


def test_user_aggregator_fuses_fragments():
    ctx = LLMContext()
    head, sink = pipeline(UserContextAggregator(context=ctx, aggregation_timeout=0.15))

    async def go():
        await head.process_frame(TranscriptionFrame(text='quero'), Direction.DOWNSTREAM)
        await asyncio.sleep(0.05)
        await head.process_frame(TranscriptionFrame(text='um café'), Direction.DOWNSTREAM)
        await asyncio.sleep(0.25)   # let the timeout fire
    run(go())
    fused = [f.text for f in of_type(sink.out, TranscriptionFrame)]
    assert fused == ['quero um café']
    assert ctx.messages[-1]['content'] == 'quero um café'


def test_assistant_aggregator_commits_full_response():
    ctx = LLMContext()
    head, sink = pipeline(AssistantContextAggregator(context=ctx))
    run(feed(head, [
        LLMTokenFrame(text='Olá '), LLMTokenFrame(text='mundo'),
        LLMFullResponseFrame(text='Olá mundo'),
    ]))
    assert ctx.messages[-1] == {'role': 'assistant', 'content': 'Olá mundo'}


def test_assistant_aggregator_commits_partial_on_interruption():
    ctx = LLMContext()
    head, sink = pipeline(AssistantContextAggregator(context=ctx))
    run(feed(head, [LLMTokenFrame(text='Eu estava dizen'), InterruptionFrame()]))
    assert ctx.messages[-1]['role'] == 'assistant'
    assert 'dizen' in ctx.messages[-1]['content']


# ─── D4 TranscriptProcessor ──────────────────────────────────────────

def test_transcript_collects_and_emits():
    seen = []
    head, sink = pipeline(TranscriptProcessor(on_update=seen.append))
    run(feed(head, [
        TranscriptionFrame(text='que horas são'),
        LLMFullResponseFrame(text='São 14h'),
    ]))
    tp = head  # the processor is the head
    assert [m['role'] for m in tp.messages] == ['user', 'assistant']
    assert [m['content'] for m in tp.messages] == ['que horas são', 'São 14h']
    assert len(seen) == 2
    assert len(of_type(sink.out, TranscriptionUpdateFrame)) == 2


def test_transcript_ignores_empty():
    head, sink = pipeline(TranscriptProcessor())
    run(feed(head, [LLMFullResponseFrame(text='   ')]))
    assert head.messages == []


# ─── D5 PipelineParams ───────────────────────────────────────────────

def test_params_defaults():
    p = PipelineParams()
    assert p.allow_interruptions is True and p.silence_gap_ms == 250
    assert p.enable_metrics is True and p.heartbeat_secs == 0.0


def test_params_from_env(monkeypatch):
    monkeypatch.setenv('LVP_ALLOW_INTERRUPTIONS', 'false')
    monkeypatch.setenv('LVP_SILENCE_GAP_MS', '400')
    monkeypatch.setenv('LVP_WATCHDOG_SECS', '5')
    p = PipelineParams.from_env()
    assert p.allow_interruptions is False
    assert p.silence_gap_ms == 400
    assert p.watchdog_secs == 5.0
