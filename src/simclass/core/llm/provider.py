from __future__ import annotations

from typing import Protocol, Sequence

from simclass.core.llm.types import ChatMessage, LLMResponse


class LLMClient(Protocol):
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        raise NotImplementedError
