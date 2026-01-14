from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Concept:
    concept_id: str
    name: str
    difficulty: float
    prerequisites: List[str]
    examples: List[str]
    exercises: List[str]


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    name: str
    concepts: List[str]


@dataclass(frozen=True)
class Unit:
    unit_id: str
    name: str
    lessons: List[Lesson]


@dataclass(frozen=True)
class Course:
    course_id: str
    name: str
    units: List[Unit]


@dataclass(frozen=True)
class PlanConcept:
    concept_id: str
    examples: List[str]
    exercises: List[str]


@dataclass(frozen=True)
class LessonPlan:
    course_id: str
    course_name: str
    unit_id: str
    lesson_id: str
    lesson_name: str
    concepts: List[PlanConcept]
    duration: int
    activity: str

    def summary(self) -> str:
        concept_lines = []
        for concept in self.concepts:
            examples = "；".join(concept.examples[:2]) if concept.examples else ""
            exercises = "；".join(concept.exercises[:1]) if concept.exercises else ""
            detail = []
            if examples:
                detail.append(f"例题:{examples}")
            if exercises:
                detail.append(f"练习:{exercises}")
            if detail:
                concept_lines.append(f"{concept.concept_id}({';'.join(detail)})")
            else:
                concept_lines.append(concept.concept_id)
        concepts_text = "、".join(concept_lines) if concept_lines else "无"
        return f"{self.lesson_name} · 知识点: {concepts_text}"


class QuestionBank:
    def __init__(self, mapping: Dict[str, List[str]]) -> None:
        self._mapping = mapping

    def question_for(self, concept_id: str, rng) -> Optional[str]:
        templates = self._mapping.get(concept_id, [])
        if not templates:
            return None
        return rng.choice(templates) if rng else templates[0]


class Curriculum:
    def __init__(
        self,
        courses: Iterable[Course],
        concepts: Iterable[Concept],
        lesson_plans: Dict[str, dict],
        question_bank: QuestionBank,
    ) -> None:
        self._courses: Dict[str, Course] = {course.course_id: course for course in courses}
        self._concepts: Dict[str, Concept] = {
            concept.concept_id: concept for concept in concepts
        }
        self._lesson_plans = lesson_plans
        self._question_bank = question_bank
        self._progress: Dict[str, int] = {}
        self._order: Dict[str, List[Tuple[str, Lesson]]] = {}
        self._concept_course: Dict[str, str] = {}
        for course in courses:
            ordered: List[Tuple[str, Lesson]] = []
            for unit in course.units:
                for lesson in unit.lessons:
                    ordered.append((unit.unit_id, lesson))
                    for concept_id in lesson.concepts:
                        self._concept_course.setdefault(concept_id, course.course_id)
            self._order[course.course_id] = ordered
            self._progress.setdefault(course.course_id, 0)

    @property
    def question_bank(self) -> QuestionBank:
        return self._question_bank

    def course_name(self, course_id: str) -> str:
        course = self._courses.get(course_id)
        return course.name if course else course_id

    def course_for_concept(self, concept_id: str) -> Optional[str]:
        return self._concept_course.get(concept_id)

    def next_lesson(self, course_id: str) -> Optional[LessonPlan]:
        ordered = self._order.get(course_id, [])
        if not ordered:
            return None
        index = self._progress.get(course_id, 0)
        if index >= len(ordered):
            index = len(ordered) - 1
        unit_id, lesson = ordered[index]
        self._progress[course_id] = min(index + 1, len(ordered))
        return self._build_plan(course_id, unit_id, lesson)

    def current_concepts(self, course_id: str) -> List[str]:
        index = max(0, self._progress.get(course_id, 0) - 1)
        ordered = self._order.get(course_id, [])
        if not ordered:
            return []
        _, lesson = ordered[min(index, len(ordered) - 1)]
        return list(lesson.concepts)

    def _build_plan(self, course_id: str, unit_id: str, lesson: Lesson) -> LessonPlan:
        course_name = self.course_name(course_id)
        plan_cfg = self._lesson_plans.get(lesson.lesson_id, {})
        concepts_cfg = plan_cfg.get("concepts", [])
        plan_concepts: List[PlanConcept] = []
        if concepts_cfg:
            for item in concepts_cfg:
                plan_concepts.append(
                    PlanConcept(
                        concept_id=str(item.get("id", "")),
                        examples=list(item.get("examples", [])),
                        exercises=list(item.get("exercises", [])),
                    )
                )
        else:
            for concept_id in lesson.concepts:
                concept = self._concepts.get(concept_id)
                plan_concepts.append(
                    PlanConcept(
                        concept_id=concept_id,
                        examples=list(concept.examples) if concept else [],
                        exercises=list(concept.exercises) if concept else [],
                    )
                )
        return LessonPlan(
            course_id=course_id,
            course_name=course_name,
            unit_id=unit_id,
            lesson_id=lesson.lesson_id,
            lesson_name=lesson.name,
            concepts=plan_concepts,
            duration=int(plan_cfg.get("duration", 40)),
            activity=str(plan_cfg.get("activity", "lecture")),
        )


def build_curriculum(cfg) -> Optional[Curriculum]:
    if not cfg:
        return None
    courses: List[Course] = []
    for item in cfg.courses:
        units: List[Unit] = []
        for unit_cfg in item.get("units", []):
            lessons: List[Lesson] = []
            for lesson_cfg in unit_cfg.get("lessons", []):
                lessons.append(
                    Lesson(
                        lesson_id=str(lesson_cfg.get("id", "")),
                        name=str(lesson_cfg.get("name", "")),
                        concepts=list(lesson_cfg.get("concepts", [])),
                    )
                )
            units.append(
                Unit(
                    unit_id=str(unit_cfg.get("id", "")),
                    name=str(unit_cfg.get("name", "")),
                    lessons=lessons,
                )
            )
        courses.append(
            Course(
                course_id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                units=units,
            )
        )
    concepts: List[Concept] = []
    for concept_cfg in cfg.concepts:
        concepts.append(
            Concept(
                concept_id=str(concept_cfg.get("id", "")),
                name=str(concept_cfg.get("name", "")),
                difficulty=float(concept_cfg.get("difficulty", 0.5)),
                prerequisites=list(concept_cfg.get("prerequisites", [])),
                examples=list(concept_cfg.get("examples", [])),
                exercises=list(concept_cfg.get("exercises", [])),
            )
        )
    question_bank = QuestionBank(cfg.question_bank)
    return Curriculum(courses, concepts, cfg.lesson_plans, question_bank)
