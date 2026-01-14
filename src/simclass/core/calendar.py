from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from simclass.app.scenario import CalendarConfig, RoutineConfig, TimetableEntry

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_CN = {
    "Mon": "周一",
    "Tue": "周二",
    "Wed": "周三",
    "Thu": "周四",
    "Fri": "周五",
    "Sat": "周六",
    "Sun": "周日",
}


def _normalize_weekday(value: str) -> str:
    if not value:
        return "Mon"
    text = value.strip()
    if text in WEEKDAYS:
        return text
    for key, cn in WEEKDAY_CN.items():
        if text == cn:
            return key
    return "Mon"


def _parse_minutes(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 2:
        return 0
    hour = int(parts[0])
    minute = int(parts[1])
    return max(0, min(23, hour)) * 60 + max(0, min(59, minute))


def _format_clock(minutes: int) -> str:
    minutes = minutes % 1440
    hour = minutes // 60
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


@dataclass(frozen=True)
class SimTime:
    tick: int
    day_index: int
    weekday: str
    weekday_cn: str
    sim_minute: int
    clock_time: str


class SimClock:
    def __init__(self, config: CalendarConfig) -> None:
        self._config = config
        self._day_minutes = max(1, int(config.day_minutes))
        self._minutes_per_tick = float(config.minutes_per_tick)
        self._start_day_index = WEEKDAYS.index(_normalize_weekday(config.start_day))
        self._start_sim_minute = self.to_sim_minutes(config.start_time)

    @property
    def day_minutes(self) -> int:
        return self._day_minutes

    @property
    def minutes_per_tick(self) -> float:
        return self._minutes_per_tick

    def to_sim_minutes(self, clock_time: str) -> int:
        real_minutes = _parse_minutes(clock_time)
        scaled = real_minutes * self._day_minutes / 1440
        return int(round(scaled))

    def to_clock_time(self, sim_minute: int) -> str:
        real_minutes = int(round(sim_minute * 1440 / self._day_minutes))
        return _format_clock(real_minutes)

    def time_for_tick(self, tick: int) -> SimTime:
        sim_total = self._start_sim_minute + (tick - 1) * self._minutes_per_tick
        day_index = int(sim_total // self._day_minutes)
        sim_minute = int(round(sim_total % self._day_minutes))
        weekday = WEEKDAYS[(self._start_day_index + day_index) % 7]
        return SimTime(
            tick=tick,
            day_index=day_index,
            weekday=weekday,
            weekday_cn=WEEKDAY_CN.get(weekday, weekday),
            sim_minute=sim_minute,
            clock_time=self.to_clock_time(sim_minute),
        )


class Timetable:
    def __init__(self, clock: SimClock, entries: Iterable[TimetableEntry]) -> None:
        self._clock = clock
        self._entries: Dict[str, Dict[int, List[TimetableEntry]]] = {}
        for entry in entries:
            for weekday in entry.weekdays:
                normalized = _normalize_weekday(weekday)
                minute = clock.to_sim_minutes(entry.start_time)
                self._entries.setdefault(normalized, {}).setdefault(minute, []).append(entry)

    def entries_for(self, weekday: str, sim_minute: int) -> List[TimetableEntry]:
        return list(self._entries.get(weekday, {}).get(sim_minute, []))

    def all_entries(self) -> List[TimetableEntry]:
        items: List[TimetableEntry] = []
        for day_entries in self._entries.values():
            for slot_entries in day_entries.values():
                items.extend(slot_entries)
        return items


class DailyRoutine:
    def __init__(
        self, clock: SimClock, config: RoutineConfig, school_days: Iterable[str]
    ) -> None:
        self._clock = clock
        self._config = config
        self._school_days = [_normalize_weekday(day) for day in school_days]
        self._weekday_actions: Dict[int, List[str]] = {}
        self._weekend_actions: Dict[int, List[str]] = {}
        self._review_breaks: List[int] = []
        self._review_home: Optional[int] = None
        self._test_start = clock.to_sim_minutes(config.test_start)
        self._test_end = clock.to_sim_minutes(config.test_end)
        self._build_actions()

    def _build_actions(self) -> None:
        self._add_action(self._weekday_actions, self._config.wake_time, "wake")
        self._add_action(self._weekday_actions, self._config.breakfast_start, "breakfast_start")
        self._add_action(self._weekday_actions, self._config.breakfast_end, "breakfast_end")
        self._add_action(self._weekday_actions, self._config.morning_class_start, "morning_classes")
        self._add_action(self._weekday_actions, self._config.test_start, "test_start")
        self._add_action(self._weekday_actions, self._config.test_end, "test_end")
        self._add_action(self._weekday_actions, self._config.lunch_start, "lunch_start")
        self._add_action(self._weekday_actions, self._config.lunch_end, "lunch_end")
        self._add_action(self._weekday_actions, self._config.afternoon_class_start, "afternoon_classes")
        self._add_action(self._weekday_actions, self._config.school_end, "school_end")
        if self._config.review_after_school:
            base = _parse_minutes(self._config.school_end)
            offset = self._config.after_school_review_offset
            review_time = _format_clock(base + offset)
            self._review_home = self._clock.to_sim_minutes(review_time)
        self._build_break_reviews()

    def _build_break_reviews(self) -> None:
        if not self._config.review_breaks:
            return
        morning_starts = _build_class_starts(
            self._config.morning_class_start,
            self._config.morning_class_count,
            self._config.class_duration,
            self._config.break_duration,
        )
        afternoon_starts = _build_class_starts(
            self._config.afternoon_class_start,
            self._config.afternoon_class_count,
            self._config.class_duration,
            self._config.break_duration,
        )
        for start in morning_starts[:-1]:
            break_start = _add_minutes(start, self._config.class_duration)
            self._review_breaks.append(self._clock.to_sim_minutes(break_start))
        for start in afternoon_starts[:-1]:
            break_start = _add_minutes(start, self._config.class_duration)
            self._review_breaks.append(self._clock.to_sim_minutes(break_start))

    def _add_action(self, target: Dict[int, List[str]], time_str: str, action: str) -> None:
        minute = self._clock.to_sim_minutes(time_str)
        target.setdefault(minute, []).append(action)

    def actions_for(self, weekday: str, sim_minute: int) -> List[str]:
        actions = (
            self._weekday_actions
            if weekday in self._school_days
            else self._weekend_actions
        )
        result = list(actions.get(sim_minute, []))
        if weekday in self._school_days and sim_minute in self._review_breaks:
            result.append("review_break")
        if (
            weekday in self._school_days
            and self._review_home is not None
            and sim_minute == self._review_home
        ):
            result.append("review_home")
        return result

    def is_test_start(self, sim_minute: int, weekday: str) -> bool:
        return weekday in self._school_days and sim_minute == self._test_start

    def is_test_window(self, sim_minute: int, weekday: str) -> bool:
        if weekday not in self._school_days:
            return False
        return self._test_start <= sim_minute <= self._test_end


def _build_class_starts(
    start_time: str, count: int, duration: int, break_duration: int
) -> List[str]:
    start_minutes = _parse_minutes(start_time)
    starts = []
    for idx in range(count):
        minutes = start_minutes + idx * (duration + break_duration)
        starts.append(_format_clock(minutes))
    return starts


def _add_minutes(time_str: str, offset: int) -> str:
    minutes = _parse_minutes(time_str) + offset
    return _format_clock(minutes)
