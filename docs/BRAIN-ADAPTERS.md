# BRAIN ADAPTERS

Logica Voice é **agnóstico de brain**. Ele só cuida dos canais (WhatsApp, Telegram, Voice) e do pipeline de áudio. A inteligência vem de fora.

Qualquer "brain" que responda **texto streaming** pode ser plugado.

---

## Interface

Todo brain implementa:

```ts
interface BrainAdapter {
  name: string;

  // Stream de resposta — recebe contexto, devolve tokens
  chat(input: BrainInput): AsyncIterable<BrainChunk>;

  // Discovery (opcional) — lista agentes disponíveis
  listAgents?(): Promise<Agent[]>;

  // Saúde
  isAlive(): Promise<boolean>;
}

interface BrainInput {
  message: string;              // texto da mensagem do usuário
  agent?: string;               // slug do agente alvo (default: principal)
  history?: Message[];          // histórico de conversa
  channel: string;              // 'whatsapp' | 'telegram' | 'voice' | 'web'
  chatId: string;               // identifier do chat
  sender: SenderIdentity;       // quem mandou
  metadata?: Record<string, any>;
}

interface BrainChunk {
  type: 'text' | 'tool_call' | 'tool_result' | 'thinking' | 'done';
  content?: string;
  toolName?: string;
  toolArgs?: any;
  metadata?: any;
}
```

---

## Adapters incluídos

### 1. OpenAI (Cloud)

```yaml
brain:
  provider: openai
  model: gpt-5            # ou gpt-4o, gpt-4-turbo
  api_key: ${OPENAI_API_KEY}
  base_url: https://api.openai.com/v1   # ou Azure, etc
```

Suporta: streaming, function calling, vision (gpt-4o-vision).

### 2. Anthropic Claude

```yaml
brain:
  provider: anthropic
  model: claude-opus-4-7  # ou sonnet-4-6, haiku-4-5
  api_key: ${ANTHROPIC_API_KEY}
  prompt_cache: true      # cache tiered (1h + 5min)
```

Suporta: streaming, tool use, prompt cache (economia ~80%).

### 3. Google Gemini

```yaml
brain:
  provider: gemini
  model: gemini-3.5-flash   # ou pro, pro-vision
  api_key: ${GEMINI_API_KEY}
```

Suporta: streaming, function calling, vision.

### 4. Ollama Local (qualquer modelo)

```yaml
brain:
  provider: ollama
  model: qwen3.5:14b      # ou llama3.3:70b, etc
  endpoint: http://localhost:11434
```

Suporta: streaming. Tools via OpenAI-compatible function calling.

### 5. MLX Local (Apple Silicon)

```yaml
brain:
  provider: mlx
  model: mlx-community/Qwen3-30B-A3B-4bit
  endpoint: http://localhost:8080   # mlx_lm.server
```

Suporta: streaming, OpenAI-compatible API.

### 6. LogicaOS (first-class integration)

```yaml
brain:
  provider: logicaos
  url: http://localhost:3001        # synapses-api
  api_key: ${LOGICAOS_BRAIN_API_KEY}
  default_agent: aurora             # CEO do LogicaOS configurado
```

**O que vem de graça com este adapter:**
- ✅ 130+ agentes catalogados (mention `@luna`, `@dev`, `@story`, etc)
- ✅ Chains multi-agent (`/chain lancamento`)
- ✅ Squads (Hackers, Segurança, Travel/Globe, Search Visibility)
- ✅ 59 clones mentor (Steve Jobs, Bourdain, etc)
- ✅ Memória pgvector persistente
- ✅ Skills (Supabase, Vercel, Playwright, etc)
- ✅ Roteamento inteligente Claude/MLX/Qwen via `llm-router.js`

### 7. Custom HTTP

Pra qualquer brain customizado que exponha endpoint streaming:

```yaml
brain:
  provider: custom
  endpoint: https://meu-brain.dev/api/chat/stream
  format: openai-compatible   # ou anthropic, sse-text
  auth:
    type: bearer
    token: ${MEU_BRAIN_TOKEN}
```

---

## Multi-brain (escolha por agente)

Caso avançado — roteamento por agente:

```yaml
agents:
  - slug: assistant
    brain: { provider: openai, model: gpt-5 }

  - slug: copywriter
    brain: { provider: anthropic, model: claude-sonnet-4-6 }

  - slug: dev
    brain: { provider: ollama, model: qwen3-coder:32b }

  - slug: aurora
    brain: { provider: logicaos, default_agent: aurora }
```

Cada `@mention` ativa um brain diferente. Custo otimizado: tarefas caras pra Claude, rápidas pra Ollama local.

---

## Built-in agents (sem brain externo)

Se você não quer plugar OpenAI/Claude/LogicaOS, Logica Voice vem com **agents.yaml** local + um orquestrador leve próprio:

```yaml
brain:
  provider: built-in
  default_llm: { provider: ollama, model: qwen3.5:14b }

agents:
  - slug: assistant
    name: "Assistente"
    system_prompt: "Você é um assistente útil em PT-BR..."
    tools: [web_search]

  - slug: cleo
    name: "Cleo"
    system_prompt: "Você é uma copywriter master..."
    tools: []
```

O built-in faz:
- Carrega `agents.yaml` ao iniciar
- Roteia mention `@cleo` pro agente certo
- Aplica system_prompt + history
- Chama o `default_llm` configurado
- Streamfica resposta

**Não é tão poderoso quanto LogicaOS Synapses** (sem chains, sem squads, sem clones), mas atende 80% dos casos pessoais/PMEs.

---

## Custom adapter (extensão)

Brain proprietário em qualquer linguagem? Implementa o protocolo HTTP:

### Requisição (POST /chat/stream)
```json
{
  "message": "Oi tudo bem?",
  "agent": "assistant",
  "history": [
    { "role": "user", "content": "Oi" },
    { "role": "assistant", "content": "Olá! Como posso ajudar?" }
  ],
  "channel": "whatsapp",
  "chatId": "user-123",
  "sender": { "phone": "+5585991420169", "displayName": "Andre" }
}
```

### Resposta (SSE — Server-Sent Events)
```
data: {"type":"text","content":"Tudo "}

data: {"type":"text","content":"bem, "}

data: {"type":"text","content":"obrigado!"}

data: {"type":"done","metadata":{"tokens_in":120,"tokens_out":3}}
```

Cabe em ~50 linhas de Node/Python/Go. Exemplos prontos em `examples/custom-brain/`.

---

## Comparação: built-in vs LogicaOS

| Feature | Built-in (agents.yaml) | LogicaOS |
|---|---|---|
| Agentes | Define localmente | 130+ pré-prontos |
| Clones mentor | ❌ | 59 (Jobs, Bourdain, etc) |
| Chains multi-agent | ❌ | ✅ (squads, waves) |
| Memória | Chroma local | pgvector Supabase |
| Tools | YAML config | 30+ pré-prontos |
| Roteamento LLM | Default fixo | Smart router (Claude/MLX/Qwen) |
| Custo | $0 (LLM externo) | $0 (LogicaOS é free) |
| Setup | 1 arquivo YAML | Install LogicaOS antes |

**Recomendação:** começa com built-in. Quando precisar de mais agentes/chains, ativa adapter LogicaOS sem mudar nada de canal/voice.

---

## Próximos adapters (roadmap)

- v0.2: **DeepSeek**, **Mistral Cloud**
- v0.3: **AWS Bedrock**, **Vertex AI** (Google Cloud)
- v0.4: **Cohere**, **Together.ai**
- v0.5: **Local: vLLM**, **TGI** (Hugging Face)

Contribuições welcome — adapter é ~50-100 linhas seguindo a interface.
