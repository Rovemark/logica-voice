# VOICE — Pipeline de áudio em detalhes

## Os 2 modos

### Modo Padrão (default)
Pipeline **STT → LLM → TTS** sequencial via Pipecat. Latência 800ms-1.5s. Usado em:
- WhatsApp/Telegram mensagens de voz (não streaming)
- Logica Voice push-to-talk
- Web chat com botão de gravar

### Modo Jarvis (opt-in)
Pipeline **speech-to-speech** direto via Moshi. Latência <200ms. Usado em:
- Logica Voice contínuo (sem botão)
- Wake word ativado
- Conversa rápida (clima, horário, comandos curtos)

---

## Modo Padrão — Pipeline Pipecat

### Arquitetura

```
[Mic capture]
    │
    ▼
[Silero VAD] ─── detecta início/fim de fala
    │
    ▼ (chunk audio quando user parar)
[faster-whisper MLX] ─── transcreve PT-BR
    │
    ▼ (texto)
[chat-loop.js do brain]
    ├─ recall memória
    ├─ system prompt tiered (cache 1h+5min)
    ├─ Claude/Qwen streaming
    └─ tools (web_search, agentes, etc)
    │
    ▼ (stream de tokens)
[Sentence buffer] ─── junta tokens em sentenças completas
    │
    ▼ (sentenças)
[Kokoro-82M ou F5-TTS] ─── synth streaming
    │
    ▼ (audio chunks 24kHz)
[Speaker output]
```

### Implementação

`packages/voice/pipeline.py`:

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.services.faster_whisper import FasterWhisperSTTService
from pipecat.services.kokoro import KokoroTTSService
from pipecat.transports.websocket import WebsocketServerTransport
from pipecat.frames.frames import LLMMessagesFrame

# LLM customizado que chama o brain LogicaOS via WebSocket
class LogicaBrainLLM(LLMService):
    async def run_llm(self, context):
        async for chunk in fetch_brain_stream(context.messages):
            yield TextFrame(chunk)

pipeline = Pipeline([
    WebsocketServerTransport(host="0.0.0.0", port=8765),
    FasterWhisperSTTService(model="large-v3", device="mlx"),
    LogicaBrainLLM(brain_url="http://localhost:3001/api/chat/stream"),
    KokoroTTSService(voice="default", sample_rate=24000),
])

await pipeline.run()
```

### Comunicação Voice App ↔ Pipecat

WebSocket binário:

```
Client → Server: { type: 'audio_in', data: <Int16Array PCM 16kHz> }
Client → Server: { type: 'config', voice_clone: 'astro' }
Client → Server: { type: 'interrupt' }

Server → Client: { type: 'transcript_partial', text: 'oi tudo bem' }
Server → Client: { type: 'transcript_final', text: 'oi tudo bem?' }
Server → Client: { type: 'agent_thinking', agent: 'astro' }
Server → Client: { type: 'response_text_chunk', text: 'Olá!' }
Server → Client: { type: 'audio_out', data: <Int16Array PCM 24kHz> }
Server → Client: { type: 'response_complete', metrics: { latency_ms: 980 } }
```

### Latência alvo

| Etapa | Tempo target |
|---|---:|
| VAD detecta fim de fala | 100ms |
| STT faster-whisper | 200-400ms |
| LLM first token (cache HIT) | 200-400ms |
| TTS Kokoro first audio chunk | 100-200ms |
| **Total round-trip** | **600-1100ms** |

---

## Modo Jarvis — Pipeline Moshi

### Arquitetura

```
[Mic stream contínuo 24kHz]
    │
    ▼
[Moshi MLX] ─── escuta + fala ao mesmo tempo
    │
    ▼
[Speaker output]
```

Moshi é **um modelo único** que processa áudio in/out simultâneo. Não há STT/LLM/TTS separados — tudo dentro do modelo.

### Implementação

`packages/voice/moshi_pipeline.py`:

```python
from moshi_mlx import models, modules
import sounddevice as sd

# Carrega modelo (~6GB, download 1x)
model = models.MoshiMLX.from_pretrained("kyutai/moshi-mlx")

# Stream bidirectional
async def jarvis_session():
    in_stream = sd.InputStream(samplerate=24000, channels=1)
    out_stream = sd.OutputStream(samplerate=24000, channels=1)

    async for audio_in in in_stream:
        async for audio_out in model.step(audio_in):
            out_stream.write(audio_out)
```

### Quando ativa
- Wake word "Astro" / "Hey Logica" detectada por OpenWakeWord
- Sessão Moshi inicia
- Auto-encerra após 30s de silêncio
- User pode encerrar com "tchau" ou botão na pill

### Limitações + workarounds
- **PT-BR fraco no Moshi original** → tem variante japonesa, comunidade trabalhando em multilang. Workaround: usar Moshi pra wake + sustentação, mas qualquer pergunta complexa transfere pro Modo Padrão.
- **Sem ferramentas (tools)** — Moshi não chama `web_search`, `email_send`, etc. Workaround: detectar intenção complexa via classifier, transferir pro Modo Padrão.
- **Memória limitada** — Moshi não acessa pgvector. Workaround: contexto curto, transcript backup pra brain depois.

### Toggle entre modos

```ts
// adapters/voice/mode-switcher.ts
class VoiceModeSwitcher {
  current: 'standard' | 'jarvis' = 'standard';

  async switchTo(mode) {
    if (mode === 'jarvis') {
      await pipecatPipeline.pause();
      await moshiPipeline.start();
    } else {
      await moshiPipeline.stop();
      await pipecatPipeline.resume();
    }
    this.current = mode;
  }
}
```

Trigger por:
- Comando `/jarvis on|off` no canal
- Botão na pill do desktop app
- Wake word "Astro modo contínuo" → switches automaticamente

---

## Voice cloning (F5-TTS)

### Setup (1x por agente)

```bash
logica voice clone astro --audio ~/Desktop/astro-reference.wav
```

Internamente:
1. Carrega F5-TTS
2. Extrai embedding do áudio (5-15s recomendado)
3. Salva em `config/voices/astro.npy`
4. Adiciona entry em `config/voices.yaml`:
   ```yaml
   voices:
     astro:
       model: f5-tts
       embedding: ./config/voices/astro.npy
       speaker_name: "Andre's clone"
       sample_rate: 24000
     luna:
       model: kokoro
       voice_id: af_sky
   ```

### Uso no pipeline

```python
# Pipecat config
KokoroTTSService(voice=lookup_voice(agent_slug='astro'))
# Ou se voice clone configurado:
F5TTSService(embedding_path='./config/voices/astro.npy')
```

### Per-agent voice
- Astro: voz personalizada do Andre (F5-TTS clone)
- Luna: voz feminina default Kokoro
- Dev: voz neutra rápida Kokoro
- Story: voz narrativa F5-TTS (clone de áudio referência)

---

## Hardware requirements

| Modo | RAM mínimo | RAM recomendado | GPU |
|---|---|---|---|
| Modo Padrão (Pipecat + faster-whisper + Kokoro) | 6GB | 12GB | Opcional |
| Modo Padrão + F5-TTS voice clone | 10GB | 16GB | Opcional |
| Modo Jarvis (Moshi MLX) | 14GB | 24GB | Apple Silicon (M2+) ou CUDA |
| Tudo simultâneo | 20GB | 32GB | Apple Silicon (M3+) |

**Default install** prioriza modo padrão (roda em qualquer Mac M1+). Modo Jarvis é opt-in pra hardware capaz.

---

## Métricas de qualidade

Cada call gera:
```json
{
  "session_id": "voice_1780000000",
  "mode": "standard",
  "stt": { "ms": 245, "tokens": 12, "model": "whisper-large-v3" },
  "llm": { "ms": 380, "tokens_in": 1245, "tokens_out": 87, "cache_hit": true },
  "tts": { "ms": 180, "chars": 234, "model": "kokoro-82m" },
  "total_ms": 805,
  "cost_usd": 0.0,
  "user_interrupted": false
}
```

Stored em `voice_sessions` table. Dashboard mostra latência p50/p95, taxa de barge-in, custo médio.

---

## Próximos passos técnicos

1. PoC mínimo: STT MLX → echo back via TTS Kokoro (sem LLM)
2. Plugar LogicaOS brain via `/api/chat/stream` existente
3. Logica Voice desktop usa WebSocket no lugar de HTTP
4. Adicionar Pipecat Smart Turn Detection
5. Toggle Moshi opt-in
