#!/usr/bin/env bash
# End-to-end smoke: boots STT + TTS + a mock LLM + the live pipeline, then runs one
# synthetic turn through it and checks the whole chain fired. No API key needed.
#
#   PYTHON=../.venv/bin/python WHISPER_MODEL=small ./run.sh
#
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENG="$(cd "$HERE/.." && pwd)"
PYTHON="${PYTHON:-python3}"
MODEL="${WHISPER_MODEL:-small}"
PIDS=()

cleanup() {
  echo "[smoke] tearing down..."
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

free_port() { lsof -ti :"$1" 2>/dev/null | xargs kill -9 2>/dev/null || true; }
for p in 8910 8911 8915 3099; do free_port "$p"; done

echo "[smoke] starting Whisper (STT, model=$MODEL)..."
"$PYTHON" "$ENG/servers/whisper_server.py" --port 8910 --model "$MODEL" >/tmp/lvp-whisper.log 2>&1 & PIDS+=($!)
echo "[smoke] starting Kokoro (TTS)..."
"$PYTHON" "$ENG/servers/kokoro_server.py" --port 8911 >/tmp/lvp-kokoro.log 2>&1 & PIDS+=($!)
echo "[smoke] starting mock LLM..."
"$PYTHON" "$HERE/mock_llm.py" 3099 >/tmp/lvp-mock.log 2>&1 & PIDS+=($!)

echo "[smoke] waiting for Kokoro to be ready (downloads models on first run)..."
for _ in $(seq 1 60); do
  curl -s -o /dev/null "http://127.0.0.1:8911/" && break
  sleep 2
done

echo "[smoke] starting live pipeline..."
LVP_LLM_URL="http://127.0.0.1:3099/llm" \
LVP_STT_URL="http://127.0.0.1:8910" LVP_TTS_URL="http://127.0.0.1:8911" \
LVP_TTS_ENGINE="kokoro" LVP_TTS_VOICE="pm_alex" \
LVP_METRICS="true" LVP_WATCHDOG_SECS="8" \
  "$PYTHON" "$ENG/live_server.py" --port 8915 >/tmp/lvp-live.log 2>&1 & PIDS+=($!)
sleep 6

echo "[smoke] running client..."
LVP_TTS_URL="http://127.0.0.1:8911" "$PYTHON" "$HERE/smoke_client.py"
RC=$?
echo "[smoke] exit code: $RC  (live server log: /tmp/lvp-live.log)"
exit $RC
