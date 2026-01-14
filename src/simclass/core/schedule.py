from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

from simclass.core.calendar import DailyRoutine, SimClock, SimTime, Timetable
from simclass.core.curriculum import Curriculum, LessonPlan


@dataclass(frozen=True)
class AcademicCalendar:
    start_date: date
    weeks: int
    holidays: List[date]
    makeup_days: List[date]
    exam_weeks: List[int]
    review_weeks: List[int]

    def date_for_day(self, day_index: int) -> date:
        return self.start_date + timedelta(days=day_index)

    def week_index(self, day_index: int) -> int:
        return day_index // 7 + 1

    def is_holiday(self, day_value: date) -> bool:
        return day_value in self.holidays and day_value not in self.makeup_days

    def is_school_day(self, day_value: date, weekday: str, school_days: List[str]) -> bool:
        if day_value in self.makeup_days:
            return True
        if day_value in self.holidays:
            return False
        return weekday in school_days


@dataclass(frozen=True)
class WeekPattern:
    name: str
    label: str
    mode: str
    extra_events: List[dict]


@dataclass(frozen=True)
class WeekInfo:
    name: str
    label: str
    mode: str


@dataclass(frozen=True)
class SemesterEventRule:
    rule_id: str
    when: dict
    set_week_type: Optional[dict]
    emit: Optional[dict]


class SemesterEventDSL:
    def __init__(self, rules: Iterable[dict]) -> None:
        self._rules: List[SemesterEventRule] = []
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id", f"rule_{index + 1}"))
            when = dict(rule.get("when", {}))
            set_week_type = rule.get("set_week_type")
            emit = rule.get("emit")
            self._rules.append(
                SemesterEventRule(
                    rule_id=rule_id,
                    when=when,
                    set_week_type=set_week_type if isinstance(set_week_type, dict) else None,
                    emit=emit if isinstance(emit, dict) else None,
                )
            )
        self._week_rules = [rule for rule in self._rules if rule.set_week_type]
        self._event_rules = [rule for rule in self._rules if rule.emit]

    def week_info_for(self, week_index: int) -> Optional[WeekInfo]:
        info: Optional[WeekInfo] = None
        for rule in self._week_rules:
            weeks = self._parse_weeks(rule.when)
            if weeks and week_index not in weeks:
                continue
            cfg = rule.set_week_type or {}
            name = str(cfg.get("name", "")).strip()
            if not name:
                continue
            label = str(cfg.get("label", name))
            mode = str(cfg.get("mode", "normal"))
            info = WeekInfo(name=name, label=label, mode=mode)
        return info

    def events_for_time(
        self,
        sim_time: SimTime,
        day_value: date,
        week_info: Optional[WeekInfo],
    ) -> List[dict]:
        events: List[dict] = []
        for rule in self._event_rules:
            if not self._match_when(rule.when, sim_time, day_value, week_info):
                continue
            payload = dict(rule.emit or {})
            payload.setdefault("type", payload.get("event_type", "announcement"))
            events.append(payload)
        return events

    def _match_when(
        self,
        when: dict,
        sim_time: SimTime,
        day_value: date,
        week_info: Optional[WeekInfo],
    ) -> bool:
        if not self._match_weeks(when, sim_time.day_index):
            return False
        if not self._match_weekday(when, sim_time.weekday):
            return False
        if not self._match_time(when, sim_time.clock_time):
            return False
        if not self._match_date(when, day_value):
            return False
        if not self._match_week_type(when, week_info):
            return False
        return True

    def _parse_weeks(self, when: dict) -> List[int]:
        if "weeks" in when and isinstance(when["weeks"], list):
            return [int(value) for value in when["weeks"] if value is not None]
        if "week" in when:
            return [int(when["week"])]
        if "week_range" in when and isinstance(when["week_range"], list):
            start, end = (when["week_range"] + [when["week_range"][-1]])[:2]
            return list(range(int(start), int(end) + 1))
        return []

    def _match_weeks(self, when: dict, day_index: int) -> bool:
        week_index = day_index // 7 + 1
        weeks = self._parse_weeks(when)
        if weeks and week_index not in weeks:
            return False
        return True

    def _match_weekday(self, when: dict, weekday: str) -> bool:
        target = when.get("weekday")
        if target and weekday != target:
            return False
        targets = when.get("weekdays")
        if targets and weekday not in targets:
            return False
        return True

    def _match_time(self, when: dict, clock_time: str) -> bool:
        target = when.get("time")
        if target and clock_time != target:
            return False
        return True

    def _match_date(self, when: dict, day_value: date) -> bool:
        target = when.get("date")
        if target and day_value.isoformat() != target:
            return False
        targets = when.get("dates")
        if targets and day_value.isoformat() not in targets:
            return False
        return True

    def _match_week_type(self, when: dict, week_info: Optional[WeekInfo]) -> bool:
        if not week_info:
            if "week_type" in when or "week_mode" in when:
                return False
            return True
        target = when.get("week_type")
        if target:
            allowed = target if isinstance(target, list) else [target]
            if week_info.name not in allowed and week_info.label not in allowed:
                return False
        target_mode = when.get("week_mode")
        if target_mode:
            allowed = target_mode if isinstance(target_mode, list) else [target_mode]
            if week_info.mode not in allowed:
                return False
        return True

@dataclass(frozen=True)
class ScheduleEvent:
    event_type: str
    payload: dict


class ScheduleGenerator:
    def __init__(
        self,
        clock: SimClock,
        routine: DailyRoutine,
        timetable: Timetable,
        calendar: AcademicCalendar,
        week_patterns: Iterable[WeekPattern],
        week_plan: List[str],
        semester_events: Optional[List[dict]],
        curriculum: Optional[Curriculum],
        rng,
        school_days: List[str],
    ) -> None:
        self._clock = clock
        self._routine = routine
        self._timetable = timetable
        self._calendar = calendar
        self._week_plan = list(week_plan)
        self._curriculum = curriculum
        self._rng = rng
        self._school_days = list(school_days)
        self._patterns: Dict[str, WeekPattern] = {
            pattern.name: pattern for pattern in week_patterns
        }
        self._semester_enabled = bool(semester_events)
        self._semester = SemesterEventDSL(semester_events or [])

    def events_for_time(self, sim_time: SimTime) -> List[ScheduleEvent]:
        events: List[ScheduleEvent] = []
        day_value = self._calendar.date_for_day(sim_time.day_index)
        week_index = self._calendar.week_index(sim_time.day_index)
        week_info = self._resolve_week_info(week_index)
        is_school_day = self._calendar.is_school_day(
            day_value, sim_time.weekday, self._school_days
        )
        if self._calendar.is_holiday(day_value):
            events.append(
                ScheduleEvent(
                    event_type="announcement",
                    payload={
                        "message": f"{sim_time.weekday_cn} {sim_time.clock_time} · 节假日",
                        "date": day_value.isoformat(),
                        "week_type": week_info.label,
                    },
                )
            )
        actions = self._routine.actions_for(sim_time.weekday, sim_time.sim_minute)
        for action in actions:
            if action in {"review_break", "review_home"}:
                events.append(
                    ScheduleEvent(
                        event_type="review",
                        payload={
                            "intensity": 0.04 if action == "review_break" else 0.06,
                            "reason": "课间回顾" if action == "review_break" else "放学回顾",
                            "clock_time": sim_time.clock_time,
                            "weekday": sim_time.weekday_cn,
                            "date": day_value.isoformat(),
                        },
                    )
                )
            else:
                events.append(
                    ScheduleEvent(
                        event_type="announcement",
                        payload={
                            "message": f"{sim_time.weekday_cn} {sim_time.clock_time} · {self._label_action(action)}",
                            "date": day_value.isoformat(),
                            "week_type": week_info.label,
                            "action": action,
                        },
                    )
                )
        if is_school_day:
            entries = self._timetable.entries_for(sim_time.weekday, sim_time.sim_minute)
            for entry in entries:
                lesson_plan = self._resolve_lesson_plan(entry.course_id)
                payload = {
                    "teacher_id": entry.teacher_id,
                    "group": entry.group,
                    "topic": entry.topic,
                    "course_id": entry.course_id,
                    "course_name": entry.topic,
                    "week_type": week_info.label,
                    "mode": week_info.mode,
                    "weekday": sim_time.weekday_cn,
                    "clock_time": sim_time.clock_time,
                    "date": day_value.isoformat(),
                }
                if lesson_plan:
                    payload.update(
                        {
                            "unit_id": lesson_plan.unit_id,
                            "lesson_id": lesson_plan.lesson_id,
                            "lesson_title": lesson_plan.lesson_name,
                            "concepts": [concept.concept_id for concept in lesson_plan.concepts],
                            "lesson_plan": lesson_plan.summary(),
                        }
                    )
                events.append(ScheduleEvent(event_type="class_session", payload=payload))
        extra_events = (
            self._semester.events_for_time(sim_time, day_value, week_info)
            if self._semester_enabled
            else self._patterns.get(
                week_info.name,
                WeekPattern(week_info.name, week_info.label, week_info.mode, []),
            ).extra_events
        )
        for extra in extra_events:
            if not self._semester_enabled and not self._matches_extra(sim_time, extra):
                continue
            events.append(
                ScheduleEvent(
                    event_type=extra.get("type", "announcement"),
                    payload={
                        "message": extra.get("message", "活动安排"),
                        "activity": extra.get("activity", extra.get("type", "")),
                        "clock_time": sim_time.clock_time,
                        "weekday": sim_time.weekday_cn,
                        "date": day_value.isoformat(),
                        "week_type": week_info.label,
                    },
                )
            )
        return events
    @property
    def curriculum(self) -> Optional[Curriculum]:
        return self._curriculum

    def is_test_start(self, sim_time: SimTime) -> bool:
        return self._routine.is_test_start(sim_time.sim_minute, sim_time.weekday)

    def day_info(self, sim_time: SimTime) -> dict:
        day_value = self._calendar.date_for_day(sim_time.day_index)
        week_index = self._calendar.week_index(sim_time.day_index)
        week_info = self._resolve_week_info(week_index)
        return {
            "date": day_value.isoformat(),
            "week_index": week_index,
            "week_type": week_info.label,
            "week_name": week_info.name,
            "week_mode": week_info.mode,
        }

    def semester_overview(self) -> dict:
        weeks = []
        for index in range(1, self._calendar.weeks + 1):
            info = self._resolve_week_info(index)
            weeks.append(
                {
                    "index": index,
                    "name": info.name,
                    "label": info.label,
                    "mode": info.mode,
                }
            )
        exam_weeks = [item["index"] for item in weeks if item["mode"] == "exam" or item["name"] == "exam"]
        review_weeks = [item["index"] for item in weeks if item["mode"] == "review" or item["name"] == "review"]
        return {
            "weeks": weeks,
            "exam_weeks": exam_weeks,
            "review_weeks": review_weeks,
            "source": "dsl" if self._semester_enabled else "legacy",
        }

    def _resolve_week_info(self, week_index: int) -> WeekInfo:
        info = self._semester.week_info_for(week_index) if self._semester_enabled else None
        if info:
            return info
        week_type = self._resolve_week_type(week_index)
        pattern = self._patterns.get(
            week_type,
            WeekPattern(week_type, week_type, "normal", []),
        )
        return WeekInfo(name=pattern.name, label=pattern.label, mode=pattern.mode)
    def _resolve_lesson_plan(self, course_id: str) -> Optional[LessonPlan]:
        if not self._curriculum:
            return None
        return self._curriculum.next_lesson(course_id)

    def _resolve_week_type(self, week_index: int) -> str:
        if week_index in self._calendar.exam_weeks:
            return "exam"
        if week_index in self._calendar.review_weeks:
            return "review"
        if self._week_plan:
            return self._week_plan[(week_index - 1) % len(self._week_plan)]
        return "A" if week_index % 2 == 1 else "B"

    def _matches_extra(self, sim_time: SimTime, extra: dict) -> bool:
        if extra.get("weekday") and extra.get("weekday") != sim_time.weekday:
            return False
        if extra.get("time") and extra.get("time") != sim_time.clock_time:
            return False
        return True

    def _label_action(self, action: str) -> str:
        mapping = {
            "wake": "起床洗漱",
            "breakfast_start": "食堂早餐",
            "breakfast_end": "早餐结束",
            "morning_classes": "上午课程开始",
            "test_start": "上午测验开始",
            "test_end": "上午测验结束",
            "lunch_start": "午餐与午休开始",
            "lunch_end": "午休结束",
            "afternoon_classes": "下午课程开始",
            "school_end": "放学回家",
        }
        return mapping.get(action, action)

def build_academic_calendar(cfg) -> AcademicCalendar:
    start_date = date.fromisoformat(cfg.start_date)
    holidays = [date.fromisoformat(value) for value in cfg.holidays]
    makeup_days = [date.fromisoformat(value) for value in cfg.makeup_days]
    return AcademicCalendar(
        start_date=start_date,
        weeks=cfg.weeks,
        holidays=holidays,
        makeup_days=makeup_days,
        exam_weeks=list(cfg.exam_weeks),
        review_weeks=list(cfg.review_weeks),
    )







