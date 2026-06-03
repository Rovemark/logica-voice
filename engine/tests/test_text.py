"""LLMContext, ToolRegistry + streaming tool-call parsing, SentenceAggregator."""

from conftest import run, pipeline, feed, of_type
from lvp.processor import Direction
from lvp.context import LLMContext
from lvp.tools import ToolRegistry, parse_streaming_tool_calls, finalize_tool_calls
from lvp.tts_processor import SentenceAggregator, clean_for_tts, extract_sentences
from lvp.frames import LLMTokenFrame, LLMFullResponseFrame, TextSentenceFrame


# ─── LLMContext ──────────────────────────────────────────────────────

def test_context_appends_turns():
    ctx = LLMContext(system='sys')
    ctx.add_user('oi')
    ctx.add_assistant('olá')
    roles = [m['role'] for m in ctx.get_messages()]
    assert roles == ['system', 'user', 'assistant']


def test_context_trim_preserves_system():
    ctx = LLMContext(system='sys', max_messages=5)
    for i in range(20):
        ctx.add_user(f'msg{i}')
    msgs = ctx.get_messages()
    assert msgs[0] == {'role': 'system', 'content': 'sys'}
    assert len(msgs) <= 5
    assert msgs[-1]['content'] == 'msg19'   # most recent kept


def test_context_tool_result_shape():
    ctx = LLMContext()
    ctx.add_tool_result('call_1', 'get_time', {'time': '14:00'})
    m = ctx.get_messages()[-1]
    assert m['role'] == 'tool' and m['tool_call_id'] == 'call_1'
    assert '14:00' in m['content']   # dict serialized to JSON string


def test_context_summarize_old():
    ctx = LLMContext(system='sys', max_messages=100)
    for i in range(20):
        ctx.add_user(f'u{i}')
        ctx.add_assistant(f'a{i}')

    async def summarizer(text):
        return 'they talked a lot'

    run(ctx.summarize_old(summarizer, keep_recent=6))
    msgs = ctx.get_messages()
    assert msgs[0]['content'] == 'sys'
    assert any('Earlier conversation summary' in (m.get('content') or '') for m in msgs)
    assert len(msgs) < 42   # compressed


# ─── ToolRegistry ────────────────────────────────────────────────────

def test_registry_execute_async_and_sync():
    reg = ToolRegistry()

    @reg.tool(name='echo', description='echo', parameters={'type': 'object', 'properties': {}})
    async def echo(args):
        return f"got {args.get('x')}"

    reg.register('add', lambda args: args['a'] + args['b'])
    assert run(reg.execute('echo', {'x': 1})) == 'got 1'
    assert run(reg.execute('add', {'a': 2, 'b': 3})) == 5


def test_registry_unknown_tool():
    reg = ToolRegistry()
    out = run(reg.execute('nope', {}))
    assert 'unknown tool' in out['error']


def test_registry_handler_error_is_caught():
    reg = ToolRegistry()
    reg.register('boom', lambda args: 1 / 0)
    out = run(reg.execute('boom', {}))
    assert 'failed' in out['error']


def test_registry_schemas():
    reg = ToolRegistry()
    reg.register('t', lambda a: None, description='desc',
                 parameters={'type': 'object', 'properties': {'x': {'type': 'string'}}})
    s = reg.schemas()[0]
    assert s['type'] == 'function' and s['function']['name'] == 't'


# ─── Streaming tool-call parsing ─────────────────────────────────────

def test_streaming_tool_call_accumulation():
    acc = {}
    # simulate OpenAI streaming deltas
    parse_streaming_tool_calls(acc, {'tool_calls': [
        {'index': 0, 'id': 'call_1', 'function': {'name': 'get_weather', 'arguments': '{"ci'}}]})
    parse_streaming_tool_calls(acc, {'tool_calls': [
        {'index': 0, 'function': {'arguments': 'ty":"SP"}'}}]})
    calls = finalize_tool_calls(acc)
    assert calls == [{'id': 'call_1', 'name': 'get_weather', 'args': {'city': 'SP'}}]


def test_finalize_skips_nameless():
    acc = {0: {'id': None, 'name': None, 'arguments': ''}}
    assert finalize_tool_calls(acc) == []


# ─── SentenceAggregator + cleaning ───────────────────────────────────

def test_clean_for_tts_strips_markdown_and_box():
    raw = "║ olá ║\n**bold** _italic_ `code`\n- item\n[link](http://x)"
    cleaned = clean_for_tts(raw)
    assert '║' not in cleaned and '*' not in cleaned and '`' not in cleaned
    assert 'olá' in cleaned and 'bold' in cleaned and 'link' in cleaned


def test_extract_sentences_keeps_incomplete_tail():
    sents, rest = extract_sentences("Frase um. Frase dois! E um resto sem fim")
    assert sents == ['Frase um.', 'Frase dois!']
    assert rest.strip() == 'E um resto sem fim'


def test_sentence_aggregator_emits_on_sentence_close():
    head, sink = pipeline(SentenceAggregator())

    async def go():
        for tok in ['Primeira ', 'frase. ', 'Segunda ', 'frase.']:
            await head.process_frame(LLMTokenFrame(text=tok), Direction.DOWNSTREAM)
        await head.process_frame(LLMFullResponseFrame(text=''), Direction.DOWNSTREAM)
    run(go())
    sents = [f.text for f in of_type(sink.out, TextSentenceFrame)]
    assert sents == ['Primeira frase.', 'Segunda frase.']
