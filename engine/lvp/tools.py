"""
tools.py — Function/tool calling for the LVP pipeline.

ToolRegistry holds named handlers + their JSON schemas. When the LLM emits tool_calls
(OpenAI streaming format), the LLMProcessor accumulates them, executes the handlers
here, appends the results to the LLMContext as {"role":"tool"} messages, and re-runs
the LLM so it can answer using the tool output. That loop is what makes it an agent.

Register a tool:
    registry = ToolRegistry()
    @registry.tool(
        name="get_weather",
        description="Get current weather for a city",
        parameters={"type":"object","properties":{"city":{"type":"string"}},"required":["city"]},
    )
    async def get_weather(args):
        return f"Sunny in {args['city']}"
"""

import asyncio
import json


class ToolRegistry:
    def __init__(self):
        self._handlers = {}   # name -> async callable(args:dict) -> result
        self._schemas = {}    # name -> OpenAI tool schema

    def register(self, name, handler, description='', parameters=None):
        self._handlers[name] = handler
        self._schemas[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters or {"type": "object", "properties": {}},
            },
        }
        return handler

    def tool(self, name, description='', parameters=None):
        """Decorator form of register()."""
        def deco(fn):
            self.register(name, fn, description, parameters)
            return fn
        return deco

    def schemas(self):
        return list(self._schemas.values())

    def has(self, name):
        return name in self._handlers

    async def execute(self, name, args, timeout=30):
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"unknown tool: {name}"}
        try:
            if asyncio.iscoroutinefunction(handler):
                return await asyncio.wait_for(handler(args), timeout=timeout)
            return handler(args)
        except asyncio.TimeoutError:
            return {"error": f"tool {name} timed out after {timeout}s"}
        except Exception as e:
            return {"error": f"tool {name} failed: {e}"}


def parse_streaming_tool_calls(accumulator, delta):
    """
    Accumulate OpenAI streaming tool_call deltas into a list of complete calls.
    `accumulator` is a dict {index: {id, name, arguments}} mutated in place.
    Returns the accumulator. Call finalize_tool_calls() when the stream ends.
    """
    for tc in (delta.get('tool_calls') or []):
        idx = tc.get('index', 0)
        slot = accumulator.setdefault(idx, {'id': None, 'name': None, 'arguments': ''})
        if tc.get('id'):
            slot['id'] = tc['id']
        fn = tc.get('function') or {}
        if fn.get('name'):
            slot['name'] = fn['name']
        if fn.get('arguments'):
            slot['arguments'] += fn['arguments']
    return accumulator


def finalize_tool_calls(accumulator):
    """Turn the accumulator into a list of {id, name, args(dict)}."""
    calls = []
    for idx in sorted(accumulator.keys()):
        slot = accumulator[idx]
        if not slot.get('name'):
            continue
        try:
            args = json.loads(slot['arguments']) if slot['arguments'] else {}
        except Exception:
            args = {}
        calls.append({'id': slot.get('id') or f'call_{idx}', 'name': slot['name'], 'args': args})
    return calls
