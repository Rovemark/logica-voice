#!/usr/bin/env bash
# Logica Voice — Python engine setup.
# Creates a venv, installs STT/TTS/VAD deps, pre-downloads models.
#
# Usage:  bash engine/setup.sh
# Time:   5-10 min first run (downloads models).

set -e
ENGINE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$ENGINE_DIR/.venv"

echo "╔══════════════════════════════════════╗"
echo "║  Logica Voice — Engine Setup         ║"
echo "╚══════════════════════════════════════╝"

command -v python3 >/dev/null 2>&1 || { echo "❌ python3 not found (brew install python3)"; exit 1; }
echo "→ Python $(python3 --version | awk '{print $2}')"

[ -d "$VENV" ] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip --quiet

echo "→ Installing core (websockets, aiohttp, numpy, silero-vad, torch)..."
pip install --quiet websockets aiohttp numpy silero-vad torch scipy

echo "→ Installing semantic turn detection (smart-turn-v3 ONNX, optional)..."
pip install --quiet onnxruntime soxr || echo "  ⚠ smart-turn deps skipped (LVP_SMART_TURN won't work)"

echo "→ Installing STT (faster-whisper)..."
pip install --quiet faster-whisper

IS_ARM=0
[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] && IS_ARM=1
if [ "$IS_ARM" = "1" ]; then
  echo "→ Apple Silicon — installing mlx-whisper (3x faster)..."
  pip install --quiet mlx-whisper || echo "  ⚠ mlx-whisper skipped"
fi

echo "→ Installing TTS — Kokoro (fast, default)..."
pip install --quiet kokoro-onnx soundfile huggingface-hub

echo "→ Optional TTS engines (Pocket TTS, Chatterbox) — install on demand:"
echo "    pip install pocket-tts        # Kyutai, PT-BR native"
echo "    pip install chatterbox-tts    # Resemble AI, voice cloning"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  ✅ Engine ready                      ║"
echo "╚══════════════════════════════════════╝"
echo "Run the pipeline:"
echo "  source engine/.venv/bin/activate"
echo "  python engine/servers/whisper_server.py --port 8910 &"
echo "  python engine/servers/kokoro_server.py  --port 8911 &"
echo "  LVP_LLM_URL=<your-llm-sse-endpoint> python engine/live_server.py --port 8915"
