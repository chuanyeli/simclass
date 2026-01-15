from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class AgentState:
    knowledge: Dict[str, float] = field(default_factory=dict)
    last_reviewed: Dict[str, int] = field(default_factory=dict)
    day_index: int = 0
    energy: float = 0.7
    attention: float = 0.7
    stress: float = 0.2
    mood: float = 0.6
    motivation: float = 0.6
    health: float = 0.8
    sleep_debt: float = 0.1
    suspicion: Dict[str, float] = field(default_factory=dict)
