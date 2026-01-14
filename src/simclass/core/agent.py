from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from simclass.core.behavior import BaseBehavior, OutboundMessage
from simclass.core.context import ContextManager
from simclass.core.directory import AgentDirectory
from simclass.core.state import AgentState
from simclass.domain import AgentProfile, Message, SystemEvent


class Agent:
    def __init__(
        self,
        profile: AgentProfile,
        bus,
        directory: AgentDirectory,
        context: Optional[ContextManager] = None,
        behavior: Optional[BaseBehavior] = None,
        memory_store=None,
        prompt: str = "",
        state: Optional[AgentState] = None,
    ) -> None:
        self.profile = profile
        self.bus = bus
        self.directory = directory
        self.context = context or ContextManager()
        self.behavior = behavior or BaseBehavior()
        self.memory_store = memory_store
        self.prompt = prompt
        self.state = state or AgentState()
        self._queue: Optional[asyncio.Queue] = None
        self._logger = logging.getLogger(f"agent.{self.profile.agent_id}")

    async def run(self) -> None:
        self._queue = await self.bus.register(self.profile.agent_id)
        if self.memory_store:
            if hasattr(self.memory_store, "load_knowledge"):
                knowledge = self.memory_store.load_knowledge(self.profile.agent_id)
                if knowledge:
                    self.state.knowledge.update(knowledge)
            recent = self.memory_store.load_recent_memory(self.profile.agent_id, limit=8)
            entries = [record.content for record in reversed(recent)]
            self.context.seed_summary(entries)
        while True:
            payload = await self._queue.get()
            if isinstance(payload, SystemEvent) and payload.event_type == "shutdown":
                self._logger.info("shutdown")
                break
            if isinstance(payload, Message):
                await self._handle_message(payload)
            elif isinstance(payload, SystemEvent):
                await self._handle_event(payload)

    async def _handle_message(self, message: Message) -> None:
        self.context.record_message(message, direction="in")
        if self.memory_store:
            self.memory_store.record_message_event(
                message, agent_id=self.profile.agent_id, direction="inbound"
            )
            self.memory_store.record_memory(
                self.profile.agent_id, "inbound", message.content, message.timestamp
            )
        actions = await self.behavior.on_message(self, message)
        await self._dispatch_actions(actions)

    async def _handle_event(self, event: SystemEvent) -> None:
        actions = await self.behavior.on_event(self, event)
        await self._dispatch_actions(actions)

    async def _dispatch_actions(self, actions: list[OutboundMessage]) -> None:
        for action in actions:
            if action.receiver_id is None:
                continue
            outbound = Message(
                sender_id=self.profile.agent_id,
                receiver_id=action.receiver_id,
                topic=action.topic,
                content=action.content,
                timestamp=time.time(),
            )
            self.context.record_message(outbound, direction="out")
            if self.memory_store:
                self.memory_store.record_message_event(
                    outbound, agent_id=self.profile.agent_id, direction="outbound"
                )
                self.memory_store.record_memory(
                    self.profile.agent_id, "outbound", action.content, outbound.timestamp
                )
            await self.bus.send(outbound)
