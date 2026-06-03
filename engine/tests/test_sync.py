"""Producer/Consumer across pipelines."""

import asyncio

from conftest import run, pipeline, of_type
from lvp.processor import Direction
from lvp.sync import ProducerProcessor, ConsumerProcessor
from lvp.frames import TranscriptionFrame, AudioInFrame


def test_producer_forwards_matching_to_consumer():
    prod = ProducerProcessor(filter=lambda f: isinstance(f, TranscriptionFrame))
    cons = ConsumerProcessor()
    prod.connect(cons)
    headA, sinkA = pipeline(prod)
    headB, sinkB = pipeline(cons)

    async def go():
        await headA.process_frame(TranscriptionFrame(text='hello'), Direction.DOWNSTREAM)
        await asyncio.sleep(0.05)   # let consumer drain
    run(go())
    a = of_type(sinkA.out, TranscriptionFrame)
    b = of_type(sinkB.out, TranscriptionFrame)
    assert a and b and b[0].text == 'hello'     # passthrough on A + delivered to B


def test_producer_filters_non_matching():
    prod = ProducerProcessor(filter=lambda f: isinstance(f, TranscriptionFrame))
    cons = ConsumerProcessor()
    prod.connect(cons)
    headA, _ = pipeline(prod)
    headB, sinkB = pipeline(cons)

    async def go():
        await headA.process_frame(AudioInFrame(pcm=b'\x00\x00'), Direction.DOWNSTREAM)
        await asyncio.sleep(0.03)
    run(go())
    assert not of_type(sinkB.out, AudioInFrame)   # audio not forwarded


def test_producer_no_passthrough():
    prod = ProducerProcessor(filter=lambda f: True, passthrough=False)
    cons = ConsumerProcessor()
    prod.connect(cons)
    headA, sinkA = pipeline(prod)
    headB, sinkB = pipeline(cons)

    async def go():
        await headA.process_frame(TranscriptionFrame(text='x'), Direction.DOWNSTREAM)
        await asyncio.sleep(0.03)
    run(go())
    assert not of_type(sinkA.out, TranscriptionFrame)   # consumed, not passed through
    assert of_type(sinkB.out, TranscriptionFrame)        # but reached B


def test_producer_transform():
    prod = ProducerProcessor(
        filter=lambda f: isinstance(f, TranscriptionFrame),
        transform=lambda f: TranscriptionFrame(text=f.text.upper()))
    cons = ConsumerProcessor()
    prod.connect(cons)
    headA, _ = pipeline(prod)
    headB, sinkB = pipeline(cons)

    async def go():
        await headA.process_frame(TranscriptionFrame(text='hi'), Direction.DOWNSTREAM)
        await asyncio.sleep(0.03)
    run(go())
    got = of_type(sinkB.out, TranscriptionFrame)
    assert got and got[0].text == 'HI'
