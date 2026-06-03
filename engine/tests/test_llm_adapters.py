"""Direct LLM adapters: OpenAI-shaped context → native Anthropic / Gemini wire format."""

from lvp.llm_adapters import AnthropicLLMProcessor, GeminiLLMProcessor


MSGS = [
    {"role": "system", "content": "Você é o Astro."},
    {"role": "user", "content": "que horas são?"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_1", "type": "function",
         "function": {"name": "get_time", "arguments": '{"tz":"BRT"}'}}]},
    {"role": "tool", "tool_call_id": "call_1", "name": "get_time",
     "content": '{"time":"14:00"}'},
]
TOOLS = [{"type": "function", "function": {
    "name": "get_time", "description": "hora atual",
    "parameters": {"type": "object", "properties": {"tz": {"type": "string"}}}}}]


# ─── Anthropic ───────────────────────────────────────────────────────

def test_anthropic_system_extracted():
    system, _ = AnthropicLLMProcessor._to_anthropic(MSGS)
    assert system == "Você é o Astro."


def test_anthropic_roles_and_tool_use():
    _, msgs = AnthropicLLMProcessor._to_anthropic(MSGS)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    tu = msgs[1]["content"][0]
    assert tu["type"] == "tool_use" and tu["name"] == "get_time" and tu["input"] == {"tz": "BRT"}


def test_anthropic_tool_result():
    _, msgs = AnthropicLLMProcessor._to_anthropic(MSGS)
    tr = msgs[2]["content"][0]
    assert tr["type"] == "tool_result" and tr["tool_use_id"] == "call_1"


def test_anthropic_tools_schema():
    ta = AnthropicLLMProcessor._tools_to_anthropic(TOOLS)
    assert ta[0]["name"] == "get_time" and "input_schema" in ta[0]


# ─── Gemini ──────────────────────────────────────────────────────────

def test_gemini_system_instruction():
    system, _ = GeminiLLMProcessor._to_gemini(MSGS)
    assert system == "Você é o Astro."


def test_gemini_roles_and_function_call():
    _, contents = GeminiLLMProcessor._to_gemini(MSGS)
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    fc = contents[1]["parts"][0]["functionCall"]
    assert fc["name"] == "get_time" and fc["args"] == {"tz": "BRT"}


def test_gemini_function_response():
    _, contents = GeminiLLMProcessor._to_gemini(MSGS)
    fr = contents[2]["parts"][0]["functionResponse"]
    assert fr["name"] == "get_time" and fr["response"] == {"time": "14:00"}


def test_gemini_tools_schema():
    tg = GeminiLLMProcessor._tools_to_gemini(TOOLS)
    decls = tg[0]["function_declarations"]
    assert decls[0]["name"] == "get_time" and "parameters" in decls[0]
