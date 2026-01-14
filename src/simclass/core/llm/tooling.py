from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: Dict[str, Any]


@dataclass(frozen=True)
class ToolContext:
    agent_id: str
    scenario: Any
    directory: Any
    memory_store: Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[[Dict[str, Any], ToolContext], str]
    input_schema: Dict[str, Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        self._tools[tool.name] = tool

    def list_allowed(self, allowlist: Iterable[str]) -> Dict[str, ToolSpec]:
        return {name: self._tools[name] for name in allowlist if name in self._tools}

    def run(self, call: ToolCall, context: ToolContext) -> str:
        tool = self._tools.get(call.name)
        if tool is None:
            raise ValueError(f"Tool not found: {call.name}")
        return tool.handler(call.args, context)


def parse_tool_call(text: str) -> Optional[ToolCall]:
    if not text:
        return None
    line = text.strip().splitlines()[0]
    if not line.startswith("TOOL:"):
        return None
    rest = line[len("TOOL:") :].strip()
    if not rest:
        return None
    if " " in rest:
        name, arg_text = rest.split(" ", 1)
    else:
        name, arg_text = rest, "{}"
    try:
        args = json.loads(arg_text) if arg_text else {}
    except json.JSONDecodeError:
        return None
    if not isinstance(args, dict):
        return None
    return ToolCall(name=name, args=args)


def format_tool_prompt(tools: Dict[str, ToolSpec]) -> str:
    if not tools:
        return "当前无可用工具。"
    lines = ["可用工具："]
    for tool in tools.values():
        lines.append(f"- {tool.name}: {tool.description} 输入结构={tool.input_schema}")
    return "\n".join(lines)
