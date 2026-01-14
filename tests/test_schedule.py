import unittest
from types import SimpleNamespace

from simclass.app.scenario import AcademicCalendarConfig, CalendarConfig, RoutineConfig, TimetableEntry
from simclass.core.calendar import DailyRoutine, SimClock, SimTime, Timetable
from simclass.core.schedule import ScheduleGenerator, WeekPattern, build_academic_calendar


class ScheduleGeneratorDSLTests(unittest.TestCase):
    def _build_generator(self):
        clock = SimClock(
            CalendarConfig(
                start_day="Mon",
                start_time="08:50",
                minutes_per_tick=1,
                day_minutes=240,
                weekdays=["Mon", "Tue", "Wed", "Thu", "Fri"],
            )
        )
        routine = DailyRoutine(
            clock,
            RoutineConfig(
                wake_time="08:00",
                breakfast_start="08:20",
                breakfast_end="08:40",
                morning_class_start="08:50",
                morning_class_count=1,
                class_duration=40,
                break_duration=10,
                test_start="11:20",
                test_end="12:00",
                lunch_start="12:00",
                lunch_end="14:00",
                afternoon_class_start="14:00",
                afternoon_class_count=0,
                school_end="18:00",
                review_breaks=True,
                review_after_school=True,
                after_school_review_offset=10,
            ),
            ["Mon", "Tue", "Wed", "Thu", "Fri"],
        )
        timetable = Timetable(
            clock,
            [
                TimetableEntry(
                    group="class_a",
                    teacher_id="t01",
                    topic="math",
                    course_id="math",
                    lesson_plan="",
                    start_time="08:50",
                    duration=40,
                    weekdays=["Mon", "Tue", "Wed", "Thu", "Fri"],
                )
            ],
        )
        calendar_cfg = AcademicCalendarConfig(
            start_date="2026-01-12",
            weeks=4,
            holidays=[],
            makeup_days=[],
            exam_weeks=[],
            review_weeks=[],
        )
        calendar = build_academic_calendar(calendar_cfg)
        week_patterns = [
            WeekPattern(name="A", label="A Week", mode="normal", extra_events=[]),
            WeekPattern(name="B", label="B Week", mode="normal", extra_events=[]),
            WeekPattern(name="exam", label="Exam Week", mode="exam", extra_events=[]),
        ]
        semester_events = [
            {
                "id": "week_a",
                "when": {"weeks": [1, 3]},
                "set_week_type": {"name": "A", "label": "A Week", "mode": "normal"},
            },
            {
                "id": "week_b",
                "when": {"weeks": [2, 4]},
                "set_week_type": {"name": "B", "label": "B Week", "mode": "normal"},
            },
            {
                "id": "exam_week",
                "when": {"weeks": [4]},
                "set_week_type": {"name": "exam", "label": "Exam Week", "mode": "exam"},
            },
            {
                "id": "club",
                "when": {"week_type": "B", "weekday": "Wed", "time": "15:40"},
                "emit": {"type": "activity", "message": "Club"},
            },
        ]
        generator = ScheduleGenerator(
            clock,
            routine,
            timetable,
            calendar,
            week_patterns,
            [],
            semester_events,
            None,
            None,
            ["Mon", "Tue", "Wed", "Thu", "Fri"],
        )
        return generator, clock

    def test_week_type_from_dsl(self):
        generator, clock = self._build_generator()
        sim_time = SimTime(
            tick=1,
            day_index=0,
            weekday="Mon",
            weekday_cn="Mon",
            sim_minute=clock.to_sim_minutes("08:50"),
            clock_time="08:50",
        )
        info = generator.day_info(sim_time)
        self.assertEqual(info["week_name"], "A")
        self.assertEqual(info["week_type"], "A Week")

    def test_dsl_extra_event(self):
        generator, clock = self._build_generator()
        sim_time = SimTime(
            tick=1,
            day_index=9,
            weekday="Wed",
            weekday_cn="Wed",
            sim_minute=clock.to_sim_minutes("15:40"),
            clock_time="15:40",
        )
        events = generator.events_for_time(sim_time)
        self.assertTrue(any(event.payload.get("message") == "Club" for event in events))

    def test_semester_overview_exam(self):
        generator, _ = self._build_generator()
        overview = generator.semester_overview()
        self.assertIn(4, overview.get("exam_weeks", []))
        week4 = next(item for item in overview["weeks"] if item["index"] == 4)
        self.assertEqual(week4["mode"], "exam")


if __name__ == "__main__":
    unittest.main()
