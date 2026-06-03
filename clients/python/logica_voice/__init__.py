"""
logica-voice-client — Python client for a live Logica Voice pipeline.

    from logica_voice import LogicaVoiceClient
"""

from .client import (
    LogicaVoiceClient, parse_event,
    SAMPLE_RATE_IN, SAMPLE_RATE_OUT, SERVER_EVENTS,
)

__all__ = [
    'LogicaVoiceClient', 'parse_event',
    'SAMPLE_RATE_IN', 'SAMPLE_RATE_OUT', 'SERVER_EVENTS',
]
__version__ = '0.1.0'
