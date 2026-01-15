import random
import unittest

from simclass.core.perception import (
    PerceptionEngine,
    build_perception_config,
    compute_probability,
)
from simclass.core.world import build_world_model
from simclass.core.directory import AgentDirectory
from simclass.domain import AgentProfile, AgentRole, Message


class TestPerception(unittest.TestCase):
    def test_distance_probability(self):
        near = compute_probability(distance=0, range_value=4, decay_mode="linear", decay_alpha=0.6)
        far = compute_probability(distance=4, range_value=4, decay_mode="linear", decay_alpha=0.6)
        self.assertGreater(near, far)
        self.assertEqual(far, 0.0)

    def test_occlusion_reduces_visibility(self):
        world = build_world_model(
            scenes_cfg=[{"id": "classroom", "type": "classroom"}],
            classroom_layout_cfg={"rows": 1, "cols": 3},
            objects_cfg=[],
        )
        world.assign_seats(["s1", "s2", "t1"], scene_id="classroom")
        directory = AgentDirectory(
            [
                AgentProfile("s1", "S1", AgentRole.STUDENT, "class_a", {}),
                AgentProfile("s2", "S2", AgentRole.STUDENT, "class_a", {}),
                AgentProfile("t1", "T1", AgentRole.TEACHER, "class_a", {}),
            ]
        )
        cfg = build_perception_config(
            {
                "enabled": True,
                "topic_channels": {"paper_note": "vision"},
                "teacher_profile": {
                    "vision_range": 4,
                    "hearing_range": 4,
                    "distance_decay": "linear",
                    "decay_alpha": 0.6,
                    "occluded_seats": ["r1c1"],
                    "occlusion_factor": 0.3,
                },
            }
        )
        engine = PerceptionEngine(world, directory, cfg, rng=random.Random(1))
        msg_occ = Message(sender_id="s1", receiver_id="t1", topic="paper_note", content="note")
        msg_clear = Message(sender_id="s2", receiver_id="t1", topic="paper_note", content="note")
        prob_occ = engine.evaluate(msg_occ, "t1").probability
        prob_clear = engine.evaluate(msg_clear, "t1").probability
        self.assertLess(prob_occ, prob_clear)

    def test_perception_differs_by_distance(self):
        world = build_world_model(
            scenes_cfg=[{"id": "classroom", "type": "classroom"}],
            classroom_layout_cfg={
                "rows": 1,
                "cols": 5,
                "empty_seats": ["r1c3", "r1c4"],
            },
            objects_cfg=[],
        )
        world.assign_seats(["s1", "s2", "t1"], scene_id="classroom")
        directory = AgentDirectory(
            [
                AgentProfile("s1", "S1", AgentRole.STUDENT, "class_a", {}),
                AgentProfile("s2", "S2", AgentRole.STUDENT, "class_a", {}),
                AgentProfile("t1", "T1", AgentRole.TEACHER, "class_a", {}),
            ]
        )
        cfg = build_perception_config(
            {
                "enabled": True,
                "topic_channels": {"noise": "hearing"},
                "default_profile": {
                    "vision_range": 4,
                    "hearing_range": 2,
                    "distance_decay": "linear",
                    "decay_alpha": 0.6,
                },
            }
        )
        engine = PerceptionEngine(world, directory, cfg, rng=random.Random(1))
        msg = Message(sender_id="s1", receiver_id="s2", topic="noise", content="noise")
        perceived_near = engine.perceive(msg, "s2")
        perceived_far = engine.perceive(msg, "t1")
        self.assertIsNotNone(perceived_near)
        self.assertIsNone(perceived_far)


if __name__ == "__main__":
    unittest.main()
