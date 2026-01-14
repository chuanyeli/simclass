from __future__ import annotations

import asyncio
import logging
from typing import Dict, Iterable


class AgentSupervisor:
    def __init__(self, restart_limit: int = 2, restart_delay: float = 0.2) -> None:
        self._restart_limit = restart_limit
        self._restart_delay = restart_delay
        self._tasks: Dict[str, asyncio.Task] = {}
        self._agents: Dict[str, object] = {}
        self._restart_counts: Dict[str, int] = {}
        self._logger = logging.getLogger("supervisor")

    def add(self, agent_id: str, agent: object) -> None:
        self._agents[agent_id] = agent
        self._restart_counts.setdefault(agent_id, 0)

    async def start(self) -> None:
        for agent_id, agent in self._agents.items():
            self._start_agent(agent_id, agent)
        await self._monitor()

    def _start_agent(self, agent_id: str, agent: object) -> None:
        task = asyncio.create_task(agent.run())
        self._tasks[agent_id] = task

    async def _monitor(self) -> None:
        while self._tasks:
            done, _ = await asyncio.wait(
                self._tasks.values(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                agent_id = self._agent_for_task(task)
                if not agent_id:
                    continue
                self._tasks.pop(agent_id, None)
                if task.cancelled():
                    continue
                exc = task.exception()
                if exc is None:
                    continue
                count = self._restart_counts.get(agent_id, 0) + 1
                self._restart_counts[agent_id] = count
                if count > self._restart_limit:
                    self._logger.error("agent %s exceeded restart limit", agent_id)
                    continue
                self._logger.warning("restarting agent %s after error: %s", agent_id, exc)
                await asyncio.sleep(self._restart_delay)
                self._start_agent(agent_id, self._agents[agent_id])

    def _agent_for_task(self, task: asyncio.Task) -> str | None:
        for agent_id, agent_task in self._tasks.items():
            if agent_task is task:
                return agent_id
        return None
