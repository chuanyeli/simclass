import unittest
from types import SimpleNamespace

from simclass.core.curriculum import build_curriculum


class CurriculumProgressionTests(unittest.TestCase):
    def test_progression_order(self):
        cfg = SimpleNamespace(
            courses=[
                {
                    "id": "math",
                    "name": "数学",
                    "units": [
                        {
                            "id": "u1",
                            "name": "基础",
                            "lessons": [
                                {"id": "l1", "name": "函数", "concepts": ["c1"]},
                                {"id": "l2", "name": "极限", "concepts": ["c2"]},
                            ],
                        }
                    ],
                }
            ],
            concepts=[
                {"id": "c1", "name": "函数定义", "difficulty": 0.3},
                {"id": "c2", "name": "极限", "difficulty": 0.4},
            ],
            lesson_plans={},
            question_bank={},
        )
        curriculum = build_curriculum(cfg)
        first = curriculum.next_lesson("math")
        second = curriculum.next_lesson("math")
        self.assertEqual(first.lesson_id, "l1")
        self.assertEqual(second.lesson_id, "l2")
        self.assertEqual(first.concepts[0].concept_id, "c1")


if __name__ == "__main__":
    unittest.main()
