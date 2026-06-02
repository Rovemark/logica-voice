# Minimal Telegram Bot

Exemplo mais simples possível — um bot Telegram com 1 agente assistente.

## Setup

```bash
# 1. Pega um token de @BotFather no Telegram
# 2. Cria projeto
npx create-logica-voice my-bot
cd my-bot

# 3. Edita logica-voice.yaml — habilita Telegram, define agente, etc

# 4. Edita .env
cat > .env <<EOF
TELEGRAM_BOT_TOKEN=123456:ABC...
OPENAI_API_KEY=sk-...
EOF

# 5. Roda
logica-voice start
```

## Config exemplo (logica-voice.yaml)

```yaml
name: my-bot

channels:
  telegram:
    enabled: true
    token: ${TELEGRAM_BOT_TOKEN}
    allowedChatIds:
      - "732596559"   # seu user_id do Telegram (descubra com @userinfobot)

brain:
  provider: built-in
  defaultLlm:
    provider: openai
    model: gpt-4o
    apiKey: ${OPENAI_API_KEY}
  defaultAgent: assistant
  agents:
    - slug: assistant
      name: Assistant
      systemPrompt: "Você é um assistente útil em PT-BR. Seja direto."
```

Pronto. Mande mensagem no bot do Telegram e ele responde via OpenAI.
