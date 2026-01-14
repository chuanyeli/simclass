from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional

from simclass.core.llm.provider import LLMClient
from simclass.core.llm.tooling import ToolContext, ToolRegistry, format_tool_prompt, parse_tool_call
from simclass.core.llm.types import ChatMessage


@dataclass(frozen=True)
class LLMPolicy:
    enabled: bool
    model: str
    temperature: float
    max_tokens: int
    tool_allowlist: List[str]
    prompt: str


class LLMResponder:
    def __init__(
        self,
        client: LLMClient,
        tool_registry: ToolRegistry,
        policy: LLMPolicy,
        scenario: Any,
        directory: Any,
        memory_store: Any,
    ) -> None:
        self._client = client
        self._tool_registry = tool_registry
        self._policy = policy
        self._scenario = scenario
        self._directory = directory
        self._memory_store = memory_store
        self._logger = logging.getLogger("llm.responder")

    async def respond(
        self,
        agent: Any,
        instruction: str,
        incoming: str,
    ) -> Optional[str]:
        if not self._policy.enabled:
            return None
        messages = self._build_messages(agent, instruction, incoming)
        response = await self._client.chat(
            messages,
            model=self._policy.model,
            temperature=self._policy.temperature,
            max_tokens=self._policy.max_tokens,
        )
        tool_call = parse_tool_call(response.content)
        if tool_call and tool_call.name not in self._policy.tool_allowlist:
            self._logger.warning("tool call not allowed: %s", tool_call.name)
            return None
        if tool_call:
            tool_context = ToolContext(
                agent_id=agent.profile.agent_id,
                scenario=self._scenario,
                directory=self._directory,
                memory_store=self._memory_store,
            )
            try:
                tool_result = self._tool_registry.run(tool_call, tool_context)
            except Exception as exc:  # noqa: BLE001
                tool_result = f"tool error: {exc}"
            messages.append(ChatMessage(role="assistant", content=response.content))
            messages.append(
                ChatMessage(
                    role="user",
                    content=f"Tool result for {tool_call.name}: {tool_result}. "
                    "Provide the final response as plain text.",
                )
            )
            response = await self._client.chat(
                messages,
                model=self._policy.model,
                temperature=self._policy.temperature,
                max_tokens=self._policy.max_tokens,
            )
        return response.content.strip()

    def _build_messages(self, agent: Any, instruction: str, incoming: str) -> List[ChatMessage]:
        tool_prompt = format_tool_prompt(
            self._tool_registry.list_allowed(self._policy.tool_allowlist)
        )
        persona = agent.profile.persona or {}
        traits = persona.get("traits", [])
        interests = persona.get("interests", [])
        persona_lines = []
        if traits:
            persona_lines.append(f"traits: {', '.join(traits)}")
        if persona.get("tone"):
            persona_lines.append(f"tone: {persona.get('tone')}")
        if interests:
            persona_lines.append(f"interests: {', '.join(interests)}")
        if persona.get("bio"):
            persona_lines.append(f"bio: {persona.get('bio')}")
        if "engagement" in persona:
            persona_lines.append(f"参与度: {persona.get('engagement')}")
        if "confidence" in persona:
            persona_lines.append(f"自信度: {persona.get('confidence')}")
        if "collaboration" in persona:
            persona_lines.append(f"协作度: {persona.get('collaboration')}")
        persona_block = "\n".join(persona_lines) if persona_lines else "none"
        system_prompt = self._policy.prompt or "你是校园模拟中的角色，请用中文简洁回应。"
        system_prompt = (
            f"{system_prompt}\n"
            "工具使用：如需工具，请仅用一行回复："
            "TOOL:tool_name {\"arg\": \"value\"}。"
            "否则只回复纯文本。"
        )
        context = agent.context.build_context()
        role_label = {
            "student": "学生",
            "teacher": "老师",
        }.get(agent.profile.role.value, agent.profile.role.value)
        user_prompt = (
            f"角色: {agent.profile.name} ({role_label})\n"
            f"分组: {agent.profile.group}\n"
            f"人设:\n{persona_block}\n"
            f"任务: {instruction}\n"
            f"输入: {incoming}\n"
            f"上下文:\n{context}\n"
            f"{tool_prompt}"
        )
        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
