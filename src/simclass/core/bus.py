from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Dict, Iterable, Optional

import logging

from simclass.domain import Message, SystemEvent


class AsyncMessageBus:
    def __init__(
        self,
        *,
        queue_maxsize: int = 100,
        send_timeout: float = 0.2,
        send_retries: int = 2,
        retry_backoff: float = 0.2,
        on_drop=None,
        message_filter=None,
        message_observer=None,
    ) -> None:
        self._queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._queue_maxsize = queue_maxsize
        self._send_timeout = send_timeout
        self._send_retries = send_retries
        self._retry_backoff = retry_backoff
        self._on_drop = on_drop
        self._message_filter = message_filter
        self._message_observer = message_observer
        self._logger = logging.getLogger("bus")

    def set_message_filter(self, message_filter) -> None:
        self._message_filter = message_filter

    def set_message_observer(self, message_observer) -> None:
        self._message_observer = message_observer

    async def register(self, agent_id: str) -> asyncio.Queue:
        async with self._lock:
            queue = self._queues.get(agent_id)
            if queue is None:
                queue = asyncio.Queue(maxsize=self._queue_maxsize)
                self._queues[agent_id] = queue
            return queue

    async def send(self, message: Message) -> None:
        if message.receiver_id is None:
            raise ValueError("receiver_id required for direct send")
        await self._deliver(
            message, message.receiver_id, apply_filter=True, apply_observer=True
        )

    async def broadcast(self, message: Message, recipients: Iterable[str]) -> None:
        for agent_id in recipients:
            queue = self._queues.get(agent_id)
            if queue is None:
                await self._handle_drop(message, reason="missing_queue")
                continue
            if message.receiver_id is None:
                outbound = Message(
                    sender_id=message.sender_id,
                    receiver_id=agent_id,
                    topic=message.topic,
                    content=message.content,
                    timestamp=message.timestamp,
                )
            else:
                outbound = message
            await self._deliver(
                outbound, agent_id, apply_filter=True, apply_observer=True
            )

    async def emit_system(self, event: SystemEvent, recipients: Iterable[str]) -> None:
        for agent_id in recipients:
            queue = self._queues.get(agent_id)
            if queue is None:
                continue
            await queue.put(event)

    async def wait_for_agents(
        self, agent_ids: Iterable[str], timeout: float = 1.0, interval: float = 0.02
    ) -> bool:
        deadline = time.monotonic() + timeout
        agent_ids = list(agent_ids)
        while time.monotonic() < deadline:
            async with self._lock:
                missing = [agent_id for agent_id in agent_ids if agent_id not in self._queues]
            if not missing:
                return True
            await asyncio.sleep(interval)
        return False

    async def _put_with_retry(self, queue: asyncio.Queue, item: Message) -> None:
        last_error: Exception | None = None
        for attempt in range(self._send_retries + 1):
            try:
                await asyncio.wait_for(queue.put(item), timeout=self._send_timeout)
                return
            except asyncio.TimeoutError as exc:
                last_error = exc
            except Exception as exc:  # noqa: BLE001
                if isinstance(exc, asyncio.CancelledError):
                    raise
                last_error = exc
                if attempt >= self._send_retries:
                    break
                await asyncio.sleep(self._retry_backoff * (attempt + 1))
        await self._handle_drop(item, reason=f"queue_full:{last_error}")

    async def _deliver(
        self,
        message: Message,
        receiver_id: str,
        *,
        apply_filter: bool,
        apply_observer: bool,
    ) -> None:
        original = message
        outbound = message
        if apply_filter and self._message_filter:
            outbound = self._message_filter(message, receiver_id)
            if outbound is None:
                return
        queue = self._queues.get(receiver_id)
        if queue is None:
            await self._handle_drop(outbound, reason="missing_queue")
            return
        await self._put_with_retry(queue, outbound)
        if apply_observer and self._message_observer:
            extras = self._message_observer(original, receiver_id) or []
            for extra in extras:
                if not extra.receiver_id:
                    continue
                await self._deliver(
                    extra,
                    extra.receiver_id,
                    apply_filter=False,
                    apply_observer=False,
                )

    async def _handle_drop(self, message: Message, reason: str) -> None:
        self._logger.warning("drop message %s (%s)", message.message_id, reason)
        if self._on_drop:
            self._on_drop(message, reason)
