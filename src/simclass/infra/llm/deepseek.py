from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Sequence

from simclass.core.llm.types import ChatMessage, LLMResponse


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str
    timeout_seconds: float
    retry_count: int
    retry_backoff: float


class DeepSeekClient:
    def __init__(self, config: DeepSeekConfig) -> None:
        self._config = config

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        payload = {
            "model": model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        raw = await self._request("/chat/completions", payload)
        content = (
            raw.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return LLMResponse(content=content, raw=raw)

    async def _request(self, path: str, payload: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(self._config.retry_count + 1):
            try:
                return await asyncio.to_thread(self._post, path, payload)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt >= self._config.retry_count:
                    break
                await asyncio.sleep(self._config.retry_backoff * (attempt + 1))
        raise RuntimeError(f"DeepSeek request failed: {last_error}")

    def _post(self, path: str, payload: dict) -> dict:
        url = self._config.base_url.rstrip("/") + path
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._config.timeout_seconds) as resp:
            text = resp.read().decode("utf-8")
        return json.loads(text)
