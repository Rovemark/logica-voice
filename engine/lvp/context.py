"""
context.py — LLM conversation context (multi-turn memory + tools).

LLMContext holds the running list of chat messages in the universal OpenAI shape:
  {"role": "system"|"user"|"assistant"|"tool", "content": ...}
plus tool definitions and tool_call bookkeeping. It's the single source of truth for
the conversation — the user aggregator appends user turns, the assistant aggregator
appends assistant turns, and tool results get appended as {"role":"tool"} messages.

This is what turns "voice that replies" into "agent that remembers and acts".
"""

import copy


class LLMContext:
    def __init__(self, system=None, tools=None, max_messages=40):
        self.messages = []
        self.tools = tools or []          # list of OpenAI-style tool schemas
        self.max_messages = max_messages
        if system:
            self.messages.append({"role": "system", "content": system})

    # ─── Turn appenders ──────────────────────────────────────────────
    def add_user(self, text):
        self.messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant(self, text, tool_calls=None):
        msg = {"role": "assistant", "content": text or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)
        self._trim()

    def add_tool_result(self, tool_call_id, name, result):
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": result if isinstance(result, str) else _to_text(result),
        })
        self._trim()

    # ─── Access ──────────────────────────────────────────────────────
    def get_messages(self):
        return copy.deepcopy(self.messages)

    def get_tools(self):
        return list(self.tools)

    def set_tools(self, tools):
        self.tools = tools or []

    def _trim(self):
        """Keep the system message + the most recent (max_messages-1) turns."""
        if len(self.messages) <= self.max_messages:
            return
        head = [m for m in self.messages[:1] if m.get("role") == "system"]
        tail = self.messages[len(head):]
        keep = tail[-(self.max_messages - len(head)):]
        self.messages = head + keep

    async def summarize_old(self, summarizer, keep_recent=8):
        """
        Compress old turns into a single summary instead of dropping them (better than
        trim for long conversations). `summarizer(text)` is an async callable returning
        a short summary string. Keeps the system message + the last `keep_recent` turns.
        """
        if len(self.messages) <= keep_recent + 2:
            return
        head = [m for m in self.messages[:1] if m.get("role") == "system"]
        tail = self.messages[len(head):]
        if len(tail) <= keep_recent:
            return
        old, recent = tail[:-keep_recent], tail[-keep_recent:]
        transcript = "\n".join(
            f"{m.get('role')}: {m.get('content','')}" for m in old if m.get('content'))
        try:
            summary = await summarizer(transcript)
        except Exception:
            return  # summarizer failed — leave context as is
        if summary:
            self.messages = head + [
                {"role": "system", "content": f"[Earlier conversation summary] {summary}"}
            ] + recent


def _to_text(obj):
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)
