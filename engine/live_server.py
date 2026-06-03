#!/usr/bin/env python3
"""
live_server.py — Logica Voice Pipeline (LVP) server.

Full-duplex de voz por arquitetura de frames (nosso "Pipecat", 100% próprio).
Pipeline: VAD → STT → LLM → SentenceAggregator → TTS → Transport.

A lógica vive em lvp/ (genérico, open source). Este arquivo só sobe o servidor.
Backends configuráveis por env:
  LVP_STT_URL    (default http://127.0.0.1:8910)   — Whisper server
  LVP_LLM_URL    (default http://127.0.0.1:3001/api/voice/llm-turn) — qualquer LLM SSE
  LVP_TTS_ENGINE (default kokoro)                  — kokoro|pocket|chatterbox
  LVP_TTS_URL    (default http://127.0.0.1:8911)
  LVP_TTS_VOICE  (default pm_alex)
  LVP_SILENCE_GAP_MS (default 250)                 — turn detection
  LVP_ECHO_TAIL_MS   (default 800)                 — echo guard
"""

import argparse
import asyncio
import os
import sys

# Permite rodar tanto como `python live_server.py` quanto importado
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lvp.runner import serve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8915)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    asyncio.run(serve(host=args.host, port=args.port))


if __name__ == '__main__':
    main()
