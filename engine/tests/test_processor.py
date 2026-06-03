"""FrameProcessor priority model: system frames bypass pause; data frames queue."""

from conftest import run, pipeline, feed, of_type
from lvp.processor import FrameProcessor, Pipeline, Direction
from lvp.frames import (
    TranscriptionFrame, InterruptionFrame, PauseFrame, ResumeFrame,
    HeartbeatFrame, StartFrame, EndFrame,
)


# The pause/queue logic lives in FrameProcessor.process_frame, so the unit under test is
# a *base* FrameProcessor placed ahead of the collecting Sink.

def test_pause_queues_data_frames():
    head, sink = pipeline(FrameProcessor())
    run(feed(head, [
        PauseFrame(),
        TranscriptionFrame(text='held1'),
        TranscriptionFrame(text='held2'),
    ]))
    # paused → data frames are queued, not delivered yet
    assert of_type(sink.out, TranscriptionFrame) == []
    # but the PauseFrame (system) passed straight through
    assert of_type(sink.out, PauseFrame)


def test_resume_drains_queue_in_order():
    head, sink = pipeline(FrameProcessor())
    run(feed(head, [
        PauseFrame(),
        TranscriptionFrame(text='a'),
        TranscriptionFrame(text='b'),
        ResumeFrame(),
    ]))
    texts = [f.text for f in of_type(sink.out, TranscriptionFrame)]
    assert texts == ['a', 'b']


def test_system_frames_bypass_pause():
    head, sink = pipeline(FrameProcessor())
    run(feed(head, [
        PauseFrame(),
        HeartbeatFrame(seq=1),     # system → must pass even while paused
        TranscriptionFrame(text='queued'),
    ]))
    assert of_type(sink.out, HeartbeatFrame)
    assert of_type(sink.out, TranscriptionFrame) == []


def test_interruption_drops_queued_data():
    head, sink = pipeline(FrameProcessor())
    run(feed(head, [
        PauseFrame(),
        TranscriptionFrame(text='doomed'),
        InterruptionFrame(),       # clears the queue
        ResumeFrame(),
    ]))
    assert of_type(sink.out, TranscriptionFrame) == []   # queued frame was dropped
    assert of_type(sink.out, InterruptionFrame)


def test_targeted_pause_only_named_processor():
    a = FrameProcessor(name='A')
    b = FrameProcessor(name='B')
    Pipeline([a, b])

    async def go():
        # pause targets B only — A keeps flowing
        await a.process_frame(PauseFrame(target='B'), Direction.DOWNSTREAM)
        await a.process_frame(TranscriptionFrame(text='x'), Direction.DOWNSTREAM)
    run(go())
    assert a._paused is False and b._paused is True


def test_start_and_end_pass_through():
    head, sink = pipeline()
    run(feed(head, [StartFrame(), EndFrame()]))
    assert of_type(sink.out, StartFrame) and of_type(sink.out, EndFrame)
