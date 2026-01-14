from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class AgentState:
    knowledge: Dict[str, float] = field(default_factory=dict)
