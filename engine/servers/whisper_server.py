#!/usr/bin/env python3
"""
whisper_server.py — HTTP server local pra STT via faster-whisper (ou mlx-whisper).

Endpoints:
  GET  /health        -> {"ok": true, "model": "large-v3", "device": "mlx"}
  POST /transcribe    -> multipart/form-data com 'audio' file -> {"text": "..."}

Auto-detecta backend: mlx-whisper se Apple Silicon, faster-whisper caso contrário.
"""
import argparse
import io
import json
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# ─── Backend detection ──────────────────────────────────────────────

def _load_backend(model_name: str, device: str):
    """Carrega o melhor backend disponível."""
    if device in ('mlx', 'auto'):
        try:
            from mlx_whisper import transcribe as mlx_transcribe
            print(f"[whisper] backend=mlx-whisper model={model_name}", flush=True)
            return {'kind': 'mlx', 'transcribe': mlx_transcribe, 'model': f'mlx-community/whisper-{model_name}-mlx'}
        except ImportError:
            if device == 'mlx':
                raise
    # Fallback: faster-whisper
    from faster_whisper import WhisperModel
    fw_device = 'auto' if device == 'auto' else device
    model = WhisperModel(model_name, device=fw_device, compute_type='auto')
    print(f"[whisper] backend=faster-whisper model={model_name} device={fw_device}", flush=True)
    return {'kind': 'fw', 'model': model}

# ─── Multipart parser simples (não usa cgi/email parser complexo) ───

def _parse_multipart(body: bytes, boundary: bytes) -> dict:
    parts = body.split(b'--' + boundary)
    out = {}
    for part in parts:
        if not part.strip() or part.strip() == b'--':
            continue
        if b'\r\n\r\n' not in part:
            continue
        head_raw, data = part.split(b'\r\n\r\n', 1)
        data = data.rstrip(b'\r\n')
        head = head_raw.decode('utf-8', errors='ignore')
        if 'name="audio"' in head:
            out['audio'] = data
        elif 'name="language"' in head:
            out['language'] = data.decode('utf-8', errors='ignore').strip()
    return out

# ─── Handler ────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    backend = None

    def log_message(self, fmt, *args):
        pass  # silencia logs default

    def _json(self, status: int, body: dict):
        data = json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if urlparse(self.path).path == '/health':
            self._json(200, {'ok': True, 'kind': self.backend['kind'] if self.backend else None})
            return
        self._json(404, {'error': 'not found'})

    def do_POST(self):
        if urlparse(self.path).path != '/transcribe':
            self._json(404, {'error': 'not found'}); return

        content_type = self.headers.get('Content-Type', '')
        content_len = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(content_len)

        # Boundary parsing
        boundary = None
        for tok in content_type.split(';'):
            tok = tok.strip()
            if tok.startswith('boundary='):
                boundary = tok.split('=', 1)[1].strip('"').encode('utf-8')
                break
        if not boundary:
            self._json(400, {'error': 'missing boundary'}); return

        try:
            fields = _parse_multipart(body, boundary)
        except Exception as e:
            self._json(400, {'error': f'parse error: {e}'}); return

        audio = fields.get('audio')
        language = fields.get('language', '') or None
        if not audio:
            self._json(400, {'error': 'missing audio field'}); return

        # Salva em tmp e transcreve
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=True) as tmp:
            tmp.write(audio)
            tmp.flush()
            try:
                if self.backend['kind'] == 'mlx':
                    result = self.backend['transcribe'](tmp.name, path_or_hf_repo=self.backend['model'], language=language)
                    text = result.get('text', '').strip()
                else:
                    segments, info = self.backend['model'].transcribe(tmp.name, language=language)
                    text = ' '.join(s.text for s in segments).strip()
            except Exception as e:
                self._json(500, {'error': f'transcribe failed: {e}'}); return

        self._json(200, {'text': text})

# ─── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8910)
    parser.add_argument('--model', default='large-v3')
    parser.add_argument('--device', default='auto')
    args = parser.parse_args()

    Handler.backend = _load_backend(args.model, args.device)

    httpd = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f"[whisper] listening on http://127.0.0.1:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
