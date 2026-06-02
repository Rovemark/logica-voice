/**
 * @logica-voice/brain-built-in
 *
 * Brain default pra Logica Voice standalone (sem LogicaOS).
 * Carrega agents de `agents.yaml`, faz routing por @mention, e chama LLM provider configurável.
 *
 * Suporta providers: openai, anthropic, ollama, mlx (qualquer endpoint OpenAI-compatible).
 */

import type {
  BrainAdapter,
  BrainInput,
  BrainChunk,
  AgentDef,
  HistoryMessage,
} from '@logica-voice/core';
import { detectMention } from '@logica-voice/core';
import { readFileSync } from 'node:fs';
import { parse as parseYaml } from 'yaml';

export interface LLMConfig {
  provider: 'openai' | 'anthropic' | 'ollama' | 'mlx' | 'custom';
  model: string;
  apiKey?: string;
  baseUrl?: string;
  temperature?: number;
  maxTokens?: number;
}

export interface BuiltInConfig {
  defaultLlm: LLMConfig;
  agents: AgentDef[];
  defaultAgent?: string;
}

export class BuiltInBrain implements BrainAdapter {
  name = 'built-in';
  private agentsBySlug = new Map<string, AgentDef>();

  constructor(private config: BuiltInConfig) {
    for (const a of config.agents) this.agentsBySlug.set(a.slug.toLowerCase(), a);
  }

  async isAlive(): Promise<boolean> {
    return true;
  }

  async listAgents(): Promise<AgentDef[]> {
    return this.config.agents;
  }

  private resolveAgent(input: BrainInput): AgentDef {
    // 1. Override explícito via input.agent
    if (input.agent && this.agentsBySlug.has(input.agent.toLowerCase())) {
      return this.agentsBySlug.get(input.agent.toLowerCase())!;
    }
    // 2. Mention no message (já parsed por adapter, mas double check)
    const mention = detectMention(input.message);
    if (mention && this.agentsBySlug.has(mention.agent)) {
      return this.agentsBySlug.get(mention.agent)!;
    }
    // 3. Default
    const def = this.config.defaultAgent && this.agentsBySlug.get(this.config.defaultAgent);
    if (def) return def;
    // 4. Primeiro disponível
    const first = this.config.agents[0];
    if (!first) throw new Error('Nenhum agente configurado no built-in brain');
    return first;
  }

  async *chat(input: BrainInput): AsyncIterable<BrainChunk> {
    const agent = this.resolveAgent(input);
    const llmCfg: LLMConfig = (agent.llm as LLMConfig) || this.config.defaultLlm;

    const messages = this._buildMessages(agent, input);

    try {
      for await (const chunk of this._callLLM(llmCfg, messages)) {
        yield chunk;
      }
    } catch (err) {
      yield { type: 'error', content: (err as Error).message };
    }
  }

  private _buildMessages(
    agent: AgentDef,
    input: BrainInput
  ): Array<{ role: 'system' | 'user' | 'assistant'; content: string }> {
    const out: Array<{ role: 'system' | 'user' | 'assistant'; content: string }> = [];
    if (agent.systemPrompt) out.push({ role: 'system', content: agent.systemPrompt });
    if (input.history) {
      for (const h of input.history) {
        out.push({ role: h.role, content: h.content });
      }
    }
    // Remove mention do texto se ainda estiver
    const mention = detectMention(input.message);
    const userText = mention ? mention.cleanText : input.message;
    out.push({ role: 'user', content: userText });
    return out;
  }

  private async *_callLLM(
    cfg: LLMConfig,
    messages: Array<{ role: string; content: string }>
  ): AsyncIterable<BrainChunk> {
    // OpenAI-compatible (também serve pra Ollama, MLX, Together, etc.)
    if (cfg.provider === 'openai' || cfg.provider === 'ollama' || cfg.provider === 'mlx' || cfg.provider === 'custom') {
      yield* this._callOpenAICompatible(cfg, messages);
      return;
    }
    if (cfg.provider === 'anthropic') {
      yield* this._callAnthropic(cfg, messages);
      return;
    }
    throw new Error(`Provider não suportado: ${cfg.provider}`);
  }

  private async *_callOpenAICompatible(
    cfg: LLMConfig,
    messages: Array<{ role: string; content: string }>
  ): AsyncIterable<BrainChunk> {
    const url = (cfg.baseUrl || 'https://api.openai.com/v1') + '/chat/completions';
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (cfg.apiKey) headers['Authorization'] = `Bearer ${cfg.apiKey}`;

    const body = {
      model: cfg.model,
      messages,
      stream: true,
      temperature: cfg.temperature ?? 0.7,
      max_tokens: cfg.maxTokens,
    };

    const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
    if (!res.ok || !res.body) {
      throw new Error(`LLM HTTP ${res.status}: ${await res.text().catch(() => '')}`);
    }

    // Parse SSE
    let buf = '';
    let totalIn = 0;
    let totalOut = 0;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const payload = trimmed.slice(5).trim();
        if (payload === '[DONE]') continue;
        try {
          const obj = JSON.parse(payload);
          const delta = obj?.choices?.[0]?.delta?.content;
          if (typeof delta === 'string' && delta.length > 0) {
            yield { type: 'text', content: delta };
          }
          if (obj?.usage) {
            totalIn = obj.usage.prompt_tokens || totalIn;
            totalOut = obj.usage.completion_tokens || totalOut;
          }
        } catch {
          // ignore malformed lines
        }
      }
    }
    yield {
      type: 'done',
      metadata: { tokensIn: totalIn, tokensOut: totalOut, model: cfg.model, provider: cfg.provider },
    };
  }

  private async *_callAnthropic(
    cfg: LLMConfig,
    messages: Array<{ role: string; content: string }>
  ): AsyncIterable<BrainChunk> {
    const url = (cfg.baseUrl || 'https://api.anthropic.com/v1') + '/messages';
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'anthropic-version': '2023-06-01',
    };
    if (cfg.apiKey) headers['x-api-key'] = cfg.apiKey;

    const system = messages.find((m) => m.role === 'system')?.content;
    const chat = messages.filter((m) => m.role !== 'system');

    const body = {
      model: cfg.model,
      max_tokens: cfg.maxTokens || 4096,
      stream: true,
      ...(system ? { system } : {}),
      messages: chat.map((m) => ({ role: m.role, content: m.content })),
    };

    const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
    if (!res.ok || !res.body) {
      throw new Error(`Anthropic HTTP ${res.status}: ${await res.text().catch(() => '')}`);
    }

    let buf = '';
    let totalIn = 0;
    let totalOut = 0;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const payload = trimmed.slice(5).trim();
        try {
          const obj = JSON.parse(payload);
          if (obj.type === 'content_block_delta' && obj.delta?.text) {
            yield { type: 'text', content: obj.delta.text };
          }
          if (obj.type === 'message_delta' && obj.usage) {
            totalOut = obj.usage.output_tokens || totalOut;
          }
          if (obj.type === 'message_start' && obj.message?.usage) {
            totalIn = obj.message.usage.input_tokens || totalIn;
          }
        } catch {
          // ignore
        }
      }
    }
    yield {
      type: 'done',
      metadata: { tokensIn: totalIn, tokensOut: totalOut, model: cfg.model, provider: cfg.provider },
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// Loader pra agents.yaml
// ═══════════════════════════════════════════════════════════════

/**
 * Carrega config do disco. Formato esperado em `agents.yaml`:
 *
 * ```yaml
 * defaultLlm:
 *   provider: openai
 *   model: gpt-4o
 *   apiKey: ${OPENAI_API_KEY}
 *
 * defaultAgent: assistant
 *
 * agents:
 *   - slug: assistant
 *     name: Assistant
 *     systemPrompt: "You are a helpful assistant."
 *   - slug: cleo
 *     name: Cleo
 *     role: Copywriter
 *     systemPrompt: "..."
 * ```
 *
 * Variáveis ${VAR} são substituídas por process.env.
 */
export function loadConfigFromFile(path: string): BuiltInConfig {
  const raw = readFileSync(path, 'utf-8');
  const interpolated = raw.replace(/\$\{([A-Z0-9_]+)\}/g, (_m, name) => {
    return process.env[name] || '';
  });
  const cfg = parseYaml(interpolated) as BuiltInConfig;
  if (!cfg?.defaultLlm) throw new Error(`Config inválida em ${path}: defaultLlm obrigatório`);
  if (!Array.isArray(cfg.agents)) throw new Error(`Config inválida em ${path}: agents[] obrigatório`);
  return cfg;
}
