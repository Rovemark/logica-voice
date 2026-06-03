#!/usr/bin/env python3
"""
chatterbox_server.py — HTTP server local pra TTS via Chatterbox Multilingual (Resemble AI).

Elo 1590 #1 TTS Arena 2026 (bate ElevenLabs v3). 500M params, MPS nativo M3.
PT-BR estável (language_id='pt'). Voice cloning few-shot via audio_prompt_path.

Endpoints:
  GET  /health      -> {"ok": true, "engine": "chatterbox", "device": "mps"}
  POST /synthesize  -> JSON {text, lang, audio_prompt_b64?, exaggeration?, cfg_weight?, temperature?}
                       -> WAV binary
"""
import argparse
import base64
import io
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

_model = None
_device = None

def _detect_device(prefer: str = "auto"):
    if prefer != "auto":
        return prefer
    try:
        import torch
        if torch.cuda.is_available(): return "cuda"
        if torch.backends.mps.is_available(): return "mps"
    except Exception:
        pass
    return "cpu"

def _load_model(device: str):
    global _model, _device
    if _model is not None and _device == device:
        return _model
    try:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    except ImportError:
        raise RuntimeError("chatterbox-tts não instalado. Rode: bash skills/logica-voice/scripts/setup.sh")

    import os
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    v3_dir = os.path.join(skill_dir, 'models', 'chatterbox-v3')
    use_v3 = os.path.exists(os.path.join(v3_dir, 't3_mtl23ls_v2.safetensors'))

    if use_v3:
        print(f"[chatterbox] carregando V3 checkpoint de {v3_dir}", flush=True)
        _model = ChatterboxMultilingualTTS.from_local(v3_dir, device=device)
    else:
        print(f"[chatterbox] V3 não encontrado em {v3_dir} — fallback pra V2 via from_pretrained", flush=True)
        _model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    _device = device
    return _model

def _synthesize_to_wav(
    text: str,
    language_id: str,
    audio_prompt_path: str = None,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
    temperature: float = 0.8,
) -> bytes:
    model = _load_model(_device)
    kwargs = {"language_id": language_id, "exaggeration": exaggeration, "cfg_weight": cfg_weight, "temperature": temperature}
    if audio_prompt_path:
        kwargs["audio_prompt_path"] = audio_prompt_path
    wav = model.generate(text, **kwargs)
    # wav é torch tensor (channels, samples) — escreve WAV direto via scipy (evita torchcodec dep)
    import numpy as np
    import scipy.io.wavfile
    arr = wav.detach().cpu().numpy() if hasattr(wav, 'detach') else np.asarray(wav)
    if arr.ndim == 2:
        # (channels, samples) -> (samples, channels) — mono fica 1D
        arr = arr.T
        if arr.shape[1] == 1:
            arr = arr[:, 0]
    if arr.dtype in (np.float32, np.float64):
        arr = np.clip(arr, -1.0, 1.0)
        arr = (arr * 32767).astype(np.int16)
    elif arr.dtype != np.int16:
        arr = arr.astype(np.int16)
    buf = io.BytesIO()
    scipy.io.wavfile.write(buf, model.sr, arr)
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
            self._json(200, {'ok': True, 'engine': 'chatterbox', 'device': _device})
            return
        self._json(404, {'error': 'not found'})

    def do_POST(self):
        if urlparse(self.path).path != '/synthesize':
            self._json(404, {'error': 'not found'}); return
        tmp_prompt = None
        try:
            content_len = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(content_len)
            payload = json.loads(body.decode('utf-8'))
            text = payload.get('text', '')
            language_id = payload.get('lang', 'pt')
            exaggeration = float(payload.get('exaggeration', 0.5))
            cfg_weight = float(payload.get('cfg_weight', 0.5))
            temperature = float(payload.get('temperature', 0.8))

            # Voice cloning: aceita audio_prompt_b64 (base64) ou audio_prompt_path
            audio_prompt_b64 = payload.get('audio_prompt_b64')
            audio_prompt_path = payload.get('audio_prompt_path')
            if audio_prompt_b64:
                tmp_prompt = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
                with open(tmp_prompt, 'wb') as f:
                    f.write(base64.b64decode(audio_prompt_b64))
                audio_prompt_path = tmp_prompt

            audio = _synthesize_to_wav(text, language_id, audio_prompt_path, exaggeration, cfg_weight, temperature)
            self._binary(200, audio, 'audio/wav')
        except Exception as e:
            import traceback
            self._json(500, {'error': str(e), 'trace': traceback.format_exc()[-600:]})
        finally:
            if tmp_prompt:
                try: os.unlink(tmp_prompt)
                except: pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8913)
    parser.add_argument('--device', default='auto')
    args = parser.parse_args()

    global _device
    _device = _detect_device(args.device)
    print(f"[chatterbox] device detectado: {_device}", flush=True)
    print(f"[chatterbox] carregando modelo multilingual (~2GB, primeira vez baixa do HF)...", flush=True)
    try:
        _load_model(_device)
        print(f"[chatterbox] modelo pronto", flush=True)
    except Exception as e:
        print(f"[chatterbox] WARN pré-load falhou: {e}", flush=True)

    httpd = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f"[chatterbox] listening on http://127.0.0.1:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
