import asyncio
import unittest

from simclass.core.behavior import StudentBehavior
from simclass.core.state import AgentState
from simclass.domain import AgentProfile, AgentRole, SystemEvent


class DummyAgent:
    def __init__(self):
        self.profile = AgentProfile(
            agent_id="s01",
            name="Student01",
            role=AgentRole.STUDENT,
            group="class_a",
            persona={},
        )
        self.state = AgentState()
        self.memory_store = None


class ForgettingTests(unittest.TestCase):
    def test_forgetting_and_review(self):
        agent = DummyAgent()
        agent.state.knowledge["math.c1"] = 0.8
        agent.state.last_reviewed["math.c1"] = 0
        behavior = StudentBehavior(responder=None, rng=None)

        asyncio.run(
            behavior.on_event(
                agent, SystemEvent("day_transition", {"day_index": 2})
            )
        )
        decayed = agent.state.knowledge["math.c1"]
        self.assertLess(decayed, 0.8)

        asyncio.run(
            behavior.on_event(
                agent,
                SystemEvent(
                    "review",
                    {"topics": ["math.c1"], "intensity": 0.05},
                ),
            )
        )
        self.assertGreater(agent.state.knowledge["math.c1"], decayed)


if __name__ == "__main__":
    unittest.main()
