import unittest
from random import Random

from simclass.core.world import ClassroomLayout, WorldModel, Scene, WorldObject


class WorldModelTests(unittest.TestCase):
    def test_seat_adjacency(self):
        layout = ClassroomLayout(rows=2, cols=2)
        world = WorldModel(
            scenes=[Scene(scene_id="classroom", scene_type="classroom")],
            layout=layout,
            objects=[],
        )
        seats = layout.available_seats()
        seat_a = seats[0]
        seat_b = seats[1]
        seat_c = seats[-1]
        self.assertTrue(world.are_adjacent(seat_a, seat_b))
        self.assertFalse(world.are_adjacent(seat_a, seat_c))

    def test_adjacent_peer_bias(self):
        layout = ClassroomLayout(rows=2, cols=2)
        world = WorldModel(
            scenes=[Scene(scene_id="classroom", scene_type="classroom")],
            layout=layout,
            objects=[],
        )
        world.assign_seats(["s1", "s2", "s3"])
        rng = Random(7)
        adjacent = 0
        non_adjacent = 0
        for _ in range(200):
            pick = world.pick_peer_with_bias("s1", ["s2", "s3"], rng, adjacency_bias=0.7)
            if pick == "s2":
                adjacent += 1
            elif pick == "s3":
                non_adjacent += 1
        self.assertGreater(adjacent, non_adjacent)

    def test_object_state_changes(self):
        layout = ClassroomLayout(rows=1, cols=1)
        obj = WorldObject(object_id="paper_note", object_type="paper_note")
        world = WorldModel(
            scenes=[Scene(scene_id="classroom", scene_type="classroom")],
            layout=layout,
            objects=[obj],
        )
        self.assertTrue(world.borrow_object("paper_note", "s1", "s2"))
        self.assertEqual(world._objects["paper_note"].state, "borrowed")
        self.assertTrue(world.return_object("paper_note"))
        self.assertEqual(world._objects["paper_note"].state, "available")


if __name__ == "__main__":
    unittest.main()
