from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from simclass.domain import Message


@dataclass
class ContextItem:
    role: str
    content: str


@dataclass
class ContextManager:
    max_items: int = 12
    summary: str = ""
    items: List[ContextItem] = field(default_factory=list)

    def record_message(self, message: Message, direction: str) -> None:
        role = "inbound" if direction == "in" else "outbound"
        self.items.append(ContextItem(role=role, content=message.content))
        if len(self.items) > self.max_items:
            self._summarize()

    def build_context(self) -> str:
        lines = []
        if self.summary:
            lines.append(f"summary: {self.summary}")
        for item in self.items:
            lines.append(f"{item.role}: {item.content}")
        return "\n".join(lines)

    def seed_summary(self, entries: List[str]) -> None:
        if not entries:
            return
        self.summary = " | ".join(entries)

    def _summarize(self) -> None:
        if not self.items:
            return
        head = self.items[:3]
        tail = self.items[-3:]
        snippet = " | ".join([item.content for item in head + tail])
        self.summary = f"{self.summary} {snippet}".strip()
        self.items = self.items[-self.max_items // 2 :]
