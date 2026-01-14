from __future__ import annotations

import logging
import os
from typing import Dict, Optional

from simclass.app.scenario import AgentSpec, LLMConfig
from simclass.core.llm.responder import LLMPolicy, LLMResponder
from simclass.infra.llm import DeepSeekClient, DeepSeekConfig


class LLMFactory:
    def __init__(self, llm_config: LLMConfig) -> None:
        self._llm_config = llm_config
        self._clients: Dict[str, Optional[object]] = {}
        self._logger = logging.getLogger("llm.factory")

    def create_responder(
        self,
        spec: AgentSpec,
        *,
        scenario,
        directory,
        memory_store,
        tool_registry,
    ) -> Optional[LLMResponder]:
        if not (self._llm_config.enabled and spec.llm.enabled):
            return None
        client = self._get_client(spec.llm.provider)
        if client is None:
            return None
        policy = LLMPolicy(
            enabled=True,
            model=spec.llm.model or self._llm_config.model,
            temperature=self._llm_config.temperature,
            max_tokens=self._llm_config.max_tokens,
            tool_allowlist=spec.llm.tools,
            prompt=spec.llm.prompt,
        )
        return LLMResponder(
            client=client,
            tool_registry=tool_registry,
            policy=policy,
            scenario=scenario,
            directory=directory,
            memory_store=memory_store,
        )

    def _get_client(self, provider: str):
        if provider in self._clients:
            return self._clients[provider]
        if provider == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            if not api_key:
                self._logger.warning("DEEPSEEK_API_KEY not set; LLM disabled")
                self._clients[provider] = None
                return None
            client = DeepSeekClient(
                DeepSeekConfig(
                    api_key=api_key,
                    base_url=self._llm_config.base_url,
                    timeout_seconds=self._llm_config.timeout_seconds,
                    retry_count=self._llm_config.retry_count,
                    retry_backoff=self._llm_config.retry_backoff,
                )
            )
            self._clients[provider] = client
            return client
        self._logger.warning("unknown provider: %s", provider)
        return None
