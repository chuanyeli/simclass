from simclass.core.agent import Agent
from simclass.core.bus import AsyncMessageBus
from simclass.core.context import ContextManager
from simclass.core.supervisor import AgentSupervisor
from simclass.core.state import AgentState

__all__ = [
    "Agent",
    "AgentState",
    "AsyncMessageBus",
    "ContextManager",
    "AgentSupervisor",
]


def __getattr__(name: str):
    if name == "Simulation":
        from simclass.core.simulation import Simulation

        return Simulation
    raise AttributeError(f"module {__name__} has no attribute {name}")
