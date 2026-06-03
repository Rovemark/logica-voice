#!/usr/bin/env python3
"""
kokoro_server.py — HTTP server local pra TTS via Kokoro-82M (ONNX).

Endpoints:
  GET  /health         -> {"ok": true}
  POST /synthesize     -> JSON {text, voice, speed, format} -> MP3/WAV binary
"""
import argparse
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# kokoro-onnx — pip install kokoro-onnx soundfile
# Modelos: kokoro-v1.0.onnx + voices-v1.0.bin (auto-download na primeira execução)

_kokoro = None  # lazy load

def _load_kokoro(model_path: str = None):
    global _kokoro
    if _kokoro is not None: return _kokoro
    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        raise RuntimeError("kokoro-onnx não instalado. Rode: bash skills/logica-voice/scripts/setup.sh")

    import os
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_dir = os.path.join(skill_dir, "models")
    model_p = os.path.join(models_dir, "kokoro-v1.0.onnx")
    voices_p = os.path.join(models_dir, "voices-v1.0.bin")

    # Fallback: auto-download se ainda não existir
    if not (os.path.exists(model_p) and os.path.exists(voices_p)):
        from huggingface_hub import hf_hub_download
        import shutil
        os.makedirs(models_dir, exist_ok=True)
        m = hf_hub_download(repo_id="fastrtc/kokoro-onnx", filename="kokoro-v1.0.onnx")
        v = hf_hub_download(repo_id="fastrtc/kokoro-onnx", filename="voices-v1.0.bin")
        shutil.copy(m, model_p)
        shutil.copy(v, voices_p)

    _kokoro = Kokoro(model_p, voices_p)
    return _kokoro

_VOICE_LANG_PREFIX = {
    'af': 'en-us', 'am': 'en-us',          # american
    'bf': 'en-gb', 'bm': 'en-gb',          # british
    'pf': 'pt-br', 'pm': 'pt-br',          # português brasileiro
    'ef': 'es',    'em': 'es',             # español
    'ff': 'fr-fr', 'fm': 'fr-fr',          # français
    'hf': 'hi',    'hm': 'hi',             # hindi
    'if': 'it',    'im': 'it',             # italiano
    'jf': 'ja',    'jm': 'ja',             # 日本語
    'zf': 'cmn',   'zm': 'cmn',            # 中文
}

def _detect_lang(voice: str, override: str = None) -> str:
    if override: return override
    prefix = (voice or '')[:2].lower()
    return _VOICE_LANG_PREFIX.get(prefix, 'en-us')

def _synthesize_to_buffer(text: str, voice: str, speed: float, fmt: str, lang: str = None) -> bytes:
    """Sintetiza áudio e retorna como bytes MP3 ou WAV.
    Lang auto-detectado pelo prefixo da voz (af/am=en-us, pf/pm=pt-br, etc) se não passado.
    """
    kokoro = _load_kokoro()
    detected_lang = _detect_lang(voice, lang)
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang=detected_lang)

    # samples é numpy array float32
    import soundfile as sf
    buf = io.BytesIO()
    if fmt == 'wav':
        sf.write(buf, samples, sample_rate, format='WAV')
    else:
        # MP3: precisa lameenc ou ffmpeg. Por default WAV (compatível com Telegram OK).
        sf.write(buf, samples, sample_rate, format='WAV')
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
            self._json(200, {'ok': True}); return
        self._json(404, {'error': 'not found'})

    def do_POST(self):
        if urlparse(self.path).path != '/synthesize':
            self._json(404, {'error': 'not found'}); return
        try:
            content_len = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(content_len)
            payload = json.loads(body.decode('utf-8'))
            text = payload.get('text', '')
            voice = payload.get('voice', 'pm_alex')
            speed = float(payload.get('speed', 1.0))
            fmt = payload.get('format', 'wav')
            lang = payload.get('lang')  # opcional — auto-detect pelo prefixo da voz
            audio = _synthesize_to_buffer(text, voice, speed, fmt, lang)
            self._binary(200, audio, 'audio/wav' if fmt == 'wav' else 'audio/mpeg')
        except Exception as e:
            self._json(500, {'error': str(e)})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8911)
    parser.add_argument('--model', default='kokoro-v1.0')
    parser.add_argument('--device', default='auto')
    args = parser.parse_args()

    # Pré-carrega modelo no boot pra primeira request ser rápida
    print(f"[kokoro] carregando modelo {args.model}...", flush=True)
    try:
        _load_kokoro()
        print(f"[kokoro] modelo pronto", flush=True)
    except Exception as e:
        print(f"[kokoro] WARN modelo não pré-carregado: {e}", flush=True)

    httpd = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f"[kokoro] listening on http://127.0.0.1:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
