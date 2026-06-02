# Voice Jarvis (modo full-duplex)

Exemplo do modo Jarvis — conversação contínua tipo Iron Man, sem botão.

> ⚠️ **v0.2 — em desenvolvimento.** Requer Moshi MLX (Apple Silicon) ou subprocess Python.

## Como vai funcionar

```bash
# 1. Instala dependências Python
pip install moshi_mlx

# 2. Cria projeto
npx create-logica-voice my-jarvis
cd my-jarvis

# 3. Edita logica-voice.yaml — voice.mode: jarvis

# 4. Roda
logica-voice start
```

## Config

```yaml
voice:
  mode: jarvis        # ativa Moshi full-duplex
  moshi:
    endpoint: ws://localhost:8998
    autoStartServer: true

channels:
  voice:
    enabled: true
    port: 8765        # WebSocket pra Logica Voice cliente desktop conectar
```

Quando rodar, o `LogicaOS Voice` (cliente desktop) conecta via WebSocket no Logica Voice (servidor) e a conversa contínua começa.
