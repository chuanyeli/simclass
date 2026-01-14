from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4


class AgentRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    SYSTEM = "system"


@dataclass(frozen=True)
class AgentProfile:
    agent_id: str
    name: str
    role: AgentRole
    group: str
    persona: dict


@dataclass(frozen=True)
class Message:
    sender_id: str
    receiver_id: Optional[str]
    topic: str
    content: str
    message_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: float = 0.0


@dataclass(frozen=True)
class SystemEvent:
    event_type: str
    payload: dict
