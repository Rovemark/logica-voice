#!/usr/bin/env python3
"""
pocket_tts_server.py — HTTP server local pra TTS via Kyutai Pocket TTS.

Modelo 100M params, CPU-only (M3 voa). PT-BR nativo (voz `rafael`).
Latência ~200ms first chunk, ~6x realtime no MacBook M3/M4.

Endpoints:
  GET  /health      -> {"ok": true, "engine": "pocket-tts", "lang": "portuguese"}
  POST /synthesize  -> JSON {text, voice, lang} -> WAV binary
"""
import argparse
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

_tts = None
_voice_cache = {}
_current_lang = None

def _load_tts(language: str):
    global _tts, _current_lang
    if _tts is not None and _current_lang == language:
        return _tts
    try:
        from pocket_tts import TTSModel
    except ImportError:
        raise RuntimeError("pocket-tts não instalado. Rode: bash skills/logica-voice/scripts/setup.sh")
    _tts = TTSModel.load_model(language=language)
    _current_lang = language
    return _tts

def _get_voice_state(voice: str):
    if voice in _voice_cache:
        return _voice_cache[voice]
    state = _tts.get_state_for_audio_prompt(voice)
    _voice_cache[voice] = state
    return state

def _synthesize_to_wav(text: str, voice: str, language: str) -> bytes:
    tts = _load_tts(language)
    state = _get_voice_state(voice)
    audio = tts.generate_audio(state, text)
    import scipy.io.wavfile
    import numpy as np
    arr = audio.numpy() if hasattr(audio, 'numpy') else np.asarray(audio)
    if arr.dtype != np.int16:
        if arr.dtype in (np.float32, np.float64):
            arr = np.clip(arr, -1.0, 1.0)
            arr = (arr * 32767).astype(np.int16)
        else:
            arr = arr.astype(np.int16)
    buf = io.BytesIO()
    scipy.io.wavfile.write(buf, tts.sample_rate, arr)
    return buf.getvalue()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _binary(self, status, data, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if urlparse(self.path).path == '/health':
            self._json(200, {'ok': True, 'engine': 'pocket-tts', 'lang': _current_lang or 'portuguese'})
            return
        self._json(404, {'error': 'not found'})

    def do_POST(self):
        if urlparse(self.path).path != '/synthesize':
            self._json(404, {'error': 'not found'}); return
        try:
            content_len = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(content_len)
            payload = json.loads(body.decode('utf-8'))
            text = payload.get('text', '')
            voice = payload.get('voice', 'rafael')
            lang = payload.get('lang', 'portuguese')
            audio = _synthesize_to_wav(text, voice, lang)
            self._binary(200, audio, 'audio/wav')
        except Exception as e:
            import traceback
            self._json(500, {'error': str(e), 'trace': traceback.format_exc()[-500:]})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8912)
    parser.add_argument('--language', default='portuguese')
    parser.add_argument('--voice', default='rafael')
    args = parser.parse_args()

    print(f"[pocket-tts] carregando modelo language={args.language}...", flush=True)
    try:
        _load_tts(args.language)
        _get_voice_state(args.voice)
        print(f"[pocket-tts] modelo pronto (voice={args.voice})", flush=True)
    except Exception as e:
        print(f"[pocket-tts] WARN pré-load falhou: {e}", flush=True)

    httpd = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f"[pocket-tts] listening on http://127.0.0.1:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
