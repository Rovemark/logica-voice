/**
 * @logica-voice/brain-logicaos
 *
 * First-class integration com LogicaOS Synapses. Quando bundled no LogicaOS install,
 * usa este adapter pra ganhar 130+ agentes, squads, chains, memória pgvector, etc.
 *
 * Endpoint usado: POST {url}/api/chat/stream (SSE response).
 */

import type { BrainAdapter, BrainInput, BrainChunk, AgentDef } from '@logica-voice/core';
import { detectMention } from '@logica-voice/core';

export interface LogicaOSBrainConfig {
  /** Ex: http://localhost:3001 */
  url: string;
  /** Brain API key (env BRAIN_API_KEY do LogicaOS) */
  apiKey?: string;
  /** Slug do CEO/agente default (ex: 'aurora', 'astro') */
  defaultAgent?: string;
  /** Habilita roteamento por @mention (default true) */
  mentionsEnabled?: boolean;
  /** Habilita comandos /squad e /chain (default true) */
  squadCommands?: boolean;
  /** Timeout em ms (default 120000) */
  timeoutMs?: number;
}

export class LogicaOSBrain implements BrainAdapter {
  name = 'logicaos';

  constructor(private config: LogicaOSBrainConfig) {}

  async isAlive(): Promise<boolean> {
    try {
      const res = await fetch(`${this.config.url}/api/health`, {
        signal: AbortSignal.timeout(3000),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  async listAgents(): Promise<AgentDef[]> {
    try {
      const res = await fetch(`${this.config.url}/api/agents`, {
        headers: this._headers(),
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) return [];
      const data = (await res.json()) as { agents?: AgentDef[] };
      return data.agents || [];
    } catch {
      return [];
    }
  }

  async *chat(input: BrainInput): AsyncIterable<BrainChunk> {
    // Detecta mention/squad/chain (passa raw pro brain decidir)
    const mention = this.config.mentionsEnabled !== false ? detectMention(input.message) : null;
    const targetAgent = input.agent || mention?.agent || this.config.defaultAgent;
    const message = mention ? mention.cleanText : input.message;

    const body = {
      message,
      agent: targetAgent,
      channel: input.channel,
      chatId: input.chatId,
      sender: input.sender,
      history: input.history,
      metadata: input.metadata,
    };

    const url = `${this.config.url}/api/chat/stream`;
    const timeoutMs = this.config.timeoutMs || 120_000;

    let res: Response;
    try {
      res = await fetch(url, {
        method: 'POST',
        headers: { ...this._headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (err) {
      yield { type: 'error', content: `LogicaOS brain unreachable: ${(err as Error).message}` };
      return;
    }

    if (!res.ok || !res.body) {
      const errText = await res.text().catch(() => '');
      yield { type: 'error', content: `LogicaOS HTTP ${res.status}: ${errText.slice(0, 200)}` };
      return;
    }

    // Parse SSE — eventos esperados:
    //   { type: 'chunk', content: string }
    //   { type: 'tool_start'|'tool_done', name, input?, output? }
    //   { type: 'citations', items: [...] }
    //   { type: 'meta', agent, tokens, duration_ms, ... }
    //   [DONE]
    let buf = '';
    let lastMeta: Record<string, unknown> = {};
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
          if (obj.type === 'chunk' && typeof obj.content === 'string') {
            yield { type: 'text', content: obj.content };
          } else if (obj.type === 'tool_start') {
            yield {
              type: 'tool_call',
              toolName: obj.name as string,
              toolArgs: (obj.input as Record<string, unknown>) || {},
            };
          } else if (obj.type === 'tool_done') {
            yield {
              type: 'tool_result',
              toolName: obj.name as string,
              metadata: { output: obj.output },
            };
          } else if (obj.type === 'meta') {
            lastMeta = obj as Record<string, unknown>;
          }
        } catch {
          // ignore malformed
        }
      }
    }

    yield { type: 'done', metadata: lastMeta };
  }

  private _headers(): Record<string, string> {
    const h: Record<string, string> = {};
    if (this.config.apiKey) h['x-api-key'] = this.config.apiKey;
    return h;
  }
}
