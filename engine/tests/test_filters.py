"""WakeCheckFilter + generic frame filters."""

from conftest import run, pipeline, feed, of_type
from lvp.processor import Direction
from lvp.filters import WakeCheckFilter, FrameFilter, FunctionFilter, NullFilter
from lvp.frames import TranscriptionFrame, InterimTranscriptionFrame, InterruptionFrame, AudioInFrame


def _texts(sink):
    return [f.text for f in of_type(sink.out, TranscriptionFrame)]


def test_wake_drops_until_wake_word():
    head, sink = pipeline(WakeCheckFilter(wake_words=('astro',), keepalive_secs=30))
    run(feed(head, [TranscriptionFrame(text='qual a previsão do tempo')]))
    assert _texts(sink) == []   # asleep → dropped


def test_wake_strips_word_and_passes_request():
    head, sink = pipeline(WakeCheckFilter(wake_words=('astro',), keepalive_secs=30))
    run(feed(head, [TranscriptionFrame(text='Astro, que horas são')]))
    assert _texts(sink) == ['que horas são']


def test_wake_only_word_waits_for_request():
    head, sink = pipeline(WakeCheckFilter(wake_words=('astro',)))
    run(feed(head, [TranscriptionFrame(text='Astro')]))
    assert _texts(sink) == []   # bare wake word → nothing to act on yet


def test_wake_stays_awake_after_wake():
    head, sink = pipeline(WakeCheckFilter(wake_words=('astro',), keepalive_secs=30))
    run(feed(head, [
        TranscriptionFrame(text='Astro, oi'),
        TranscriptionFrame(text='e o clima'),     # no wake word, but still awake
    ]))
    assert _texts(sink) == ['oi', 'e o clima']


def test_wake_passes_system_frames():
    head, sink = pipeline(WakeCheckFilter())
    run(feed(head, [InterruptionFrame()]))
    assert of_type(sink.out, InterruptionFrame)


def test_frame_filter_allows_only_listed():
    head, sink = pipeline(FrameFilter(allowed_types=(TranscriptionFrame,)))
    run(feed(head, [TranscriptionFrame(text='keep'), AudioInFrame(pcm=b'\x00')]))
    assert of_type(sink.out, TranscriptionFrame) and not of_type(sink.out, AudioInFrame)


def test_function_filter_predicate():
    head, sink = pipeline(FunctionFilter(predicate=lambda f: getattr(f, 'text', '') == 'yes'))
    run(feed(head, [TranscriptionFrame(text='yes'), TranscriptionFrame(text='no')]))
    assert _texts(sink) == ['yes']


def test_null_filter_blocks_data():
    head, sink = pipeline(NullFilter())
    run(feed(head, [TranscriptionFrame(text='blocked')]))
    assert _texts(sink) == []
