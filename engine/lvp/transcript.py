"""
transcript.py — structured running transcript of the conversation.

Watches user TranscriptionFrames and assistant LLMFullResponseFrames flowing by, keeps an
ordered list of {role, content, at}, and on each new message emits a
TranscriptionUpdateFrame and fires an optional on_update(message) callback. Transparent —
frames pass through untouched. Great for a live transcript pane, audit logs, or building a
dataset.

    tp = TranscriptProcessor(on_update=lambda m: print(m['role'], m['content']))
    # ... place anywhere downstream of STT + LLM ...
    tp.messages   # [{'role':'user','content':...,'at':...}, {'role':'assistant',...}]
"""

from .processor import FrameProcessor, Direction
from .frames import TranscriptionFrame, LLMFullResponseFrame, TranscriptionUpdateFrame


class TranscriptProcessor(FrameProcessor):
    def __init__(self, on_update=None, name=None):
        super().__init__(name)
        self.on_update = on_update
        self.messages = []

    async def process_frame(self, frame, direction):
        role = content = None
        if isinstance(frame, TranscriptionFrame):
            role, content = 'user', frame.text
        elif isinstance(frame, LLMFullResponseFrame):
            role, content = 'assistant', frame.text

        if role and content and content.strip():
            msg = {'role': role, 'content': content.strip(), 'at': frame.ts}
            self.messages.append(msg)
            if self.on_update:
                try:
                    self.on_update(msg)
                except Exception:
                    pass
            await self.push_frame(
                TranscriptionUpdateFrame(role=role, content=msg['content'], at=frame.ts),
                Direction.DOWNSTREAM)

        await super().process_frame(frame, direction)
