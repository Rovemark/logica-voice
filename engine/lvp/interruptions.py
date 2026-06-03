"""
interruptions.py — when does the user's voice actually count as a barge-in?

By default any voiced frame while the bot is speaking interrupts it. That's twitchy: a
cough, an "uh-huh", or a door slam cuts the bot off. An InterruptionStrategy decides
whether an in-progress user utterance is *intentional* enough to interrupt.

  AlwaysInterruptStrategy        : interrupt on any voice (legacy default)
  MinSpeechDurationStrategy      : require N ms of sustained voice (rejects clicks/blips)
  MinWordsInterruptionStrategy   : require N transcribed words (needs interim STT text)

The VAD feeds voiced-audio duration via append_audio(); a streaming-STT path can feed
interim text via append_text(). reset() is called when the bot stops speaking.
"""


class InterruptionStrategy:
    def reset(self):
        pass

    def append_audio(self, ms: float):
        pass

    def append_text(self, text: str):
        pass

    def should_interrupt(self) -> bool:
        raise NotImplementedError


class AlwaysInterruptStrategy(InterruptionStrategy):
    def should_interrupt(self) -> bool:
        return True


class MinSpeechDurationStrategy(InterruptionStrategy):
    """Interrupt only after `min_ms` of sustained voiced audio while the bot speaks."""

    def __init__(self, min_ms: float = 300.0):
        self.min_ms = min_ms
        self._ms = 0.0

    def reset(self):
        self._ms = 0.0

    def append_audio(self, ms: float):
        self._ms += ms

    def should_interrupt(self) -> bool:
        return self._ms >= self.min_ms


class MinWordsInterruptionStrategy(InterruptionStrategy):
    """Interrupt only once the interim transcription has at least `min_words` words."""

    def __init__(self, min_words: int = 2):
        self.min_words = min_words
        self._text = ''

    def reset(self):
        self._text = ''

    def append_text(self, text: str):
        self._text = text or ''

    def should_interrupt(self) -> bool:
        return len(self._text.split()) >= self.min_words
