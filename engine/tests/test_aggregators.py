"""PatternAggregator (hide <thinking>), DTMFAggregator, WordAggregator."""

from conftest import run, pipeline, feed, of_type
from lvp.processor import Direction
from lvp.aggregators import PatternAggregator, DTMFAggregator, WordAggregator
from lvp.frames import (
    LLMTokenFrame, LLMFullResponseFrame, InputDTMFFrame,
    TranscriptionFrame, WordTimestampFrame,
)


def _spoken(sink):
    return ''.join(f.text for f in of_type(sink.out, LLMTokenFrame))


def test_pattern_hides_thinking_block():
    head, sink = pipeline(PatternAggregator())
    text = "Oi <thinking>calcular 2+2</thinking>a resposta é quatro."

    async def go():
        for ch in text:
            await head.process_frame(LLMTokenFrame(text=ch), Direction.DOWNSTREAM)
        await head.process_frame(LLMFullResponseFrame(text=text), Direction.DOWNSTREAM)
    run(go())
    spoken = _spoken(sink)
    assert '<thinking>' not in spoken and 'calcular' not in spoken
    assert 'Oi' in spoken and 'quatro' in spoken


def test_pattern_passes_clean_text_untouched():
    head, sink = pipeline(PatternAggregator())
    text = "tudo certo por aqui."

    async def go():
        for ch in text:
            await head.process_frame(LLMTokenFrame(text=ch), Direction.DOWNSTREAM)
        await head.process_frame(LLMFullResponseFrame(text=text), Direction.DOWNSTREAM)
    run(go())
    assert _spoken(sink) == text


def test_pattern_tag_split_across_chunks():
    # the open tag arrives in pieces — must still be detected
    head, sink = pipeline(PatternAggregator())
    chunks = ["before <thin", "king>secret</think", "ing> after"]

    async def go():
        for c in chunks:
            await head.process_frame(LLMTokenFrame(text=c), Direction.DOWNSTREAM)
        await head.process_frame(LLMFullResponseFrame(text=''), Direction.DOWNSTREAM)
    run(go())
    spoken = _spoken(sink)
    assert 'secret' not in spoken
    assert 'before' in spoken and 'after' in spoken


def test_dtmf_terminator_emits_turn():
    head, sink = pipeline(DTMFAggregator(terminators=('#',)))
    run(feed(head, [InputDTMFFrame(digit=d) for d in '123#']))
    trans = of_type(sink.out, TranscriptionFrame)
    assert trans and trans[0].text == 'DTMF: 123'


def test_dtmf_forwards_raw_keys():
    head, sink = pipeline(DTMFAggregator())
    run(feed(head, [InputDTMFFrame(digit='5')]))
    assert of_type(sink.out, InputDTMFFrame)   # raw key still flows


def test_word_aggregator_fans_out_timestamps():
    head, sink = pipeline(WordAggregator())
    tf = TranscriptionFrame(text='oi astro', words=[
        {'word': 'oi', 'start': 0.0}, {'word': 'astro', 'start': 0.3}])
    run(feed(head, [tf]))
    wts = of_type(sink.out, WordTimestampFrame)
    assert [(w.word, w.time) for w in wts] == [('oi', 0.0), ('astro', 0.3)]
    assert of_type(sink.out, TranscriptionFrame)   # original still passes


def test_word_aggregator_noop_without_words():
    head, sink = pipeline(WordAggregator())
    run(feed(head, [TranscriptionFrame(text='sem timing')]))
    assert not of_type(sink.out, WordTimestampFrame)
    assert of_type(sink.out, TranscriptionFrame)
