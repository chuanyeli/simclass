from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
from uuid import uuid4

from simclass.domain import SystemEvent


@dataclass(frozen=True)
class ClassControllerConfig:
    lecture_ticks: int
    question_ticks: int
    group_ticks: int
    summary_ticks: int


@dataclass(frozen=True)
class ScheduledPhase:
    tick: int
    event: SystemEvent


class ClassroomController:
    def __init__(self, config: ClassControllerConfig) -> None:
        self._config = config
        self._queue: List[ScheduledPhase] = []

    def register_session(self, start_tick: int, payload: dict) -> None:
        session_id = payload.get("session_id") or str(uuid4())
        base = dict(payload)
        base["session_id"] = session_id
        lecture_tick = start_tick
        question_tick = lecture_tick + self._config.lecture_ticks
        group_tick = question_tick + self._config.question_ticks
        summary_tick = group_tick + self._config.group_ticks
        self._queue.extend(
            [
                ScheduledPhase(
                    tick=lecture_tick,
                    event=SystemEvent("phase_lecture", base),
                ),
                ScheduledPhase(
                    tick=question_tick,
                    event=SystemEvent("phase_questions", base),
                ),
                ScheduledPhase(
                    tick=group_tick,
                    event=SystemEvent("group_discussion", base),
                ),
                ScheduledPhase(
                    tick=summary_tick,
                    event=SystemEvent("phase_summary", base),
                ),
            ]
        )

    def due_events(self, tick: int) -> List[SystemEvent]:
        due = [item for item in self._queue if item.tick == tick]
        if due:
            self._queue = [item for item in self._queue if item.tick != tick]
        return [item.event for item in due]
