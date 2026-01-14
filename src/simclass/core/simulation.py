from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import List, Optional

from simclass.core.agent import Agent
from simclass.core.behavior import StudentBehavior, TeacherBehavior
from simclass.core.bus import AsyncMessageBus
from simclass.core.calendar import DailyRoutine, SimClock, Timetable
from simclass.core.curriculum import build_curriculum
from simclass.core.schedule import ScheduleGenerator, WeekPattern, build_academic_calendar
from simclass.core.social import build_social_graph
from simclass.core.context import ContextManager
from simclass.core.controller import ClassroomController, ClassControllerConfig
from simclass.core.directory import AgentDirectory
from simclass.core.supervisor import AgentSupervisor
from simclass.domain import AgentRole, Message, SystemEvent


class Simulation:
    def __init__(
        self,
        scenario,
        memory_store,
        llm_factory,
        tool_registry,
        start_tick: int = 1,
    ) -> None:
        self._scenario = scenario
        self._memory_store = memory_store
        self._bus = AsyncMessageBus(
            queue_maxsize=scenario.runtime.queue_maxsize,
            send_timeout=scenario.runtime.send_timeout,
            send_retries=scenario.runtime.send_retries,
            retry_backoff=scenario.runtime.retry_backoff,
            on_drop=self._memory_store.record_dead_letter,
        )
        self._directory = AgentDirectory(
            [spec.profile for spec in scenario.agent_specs]
        )
        self._agents: List[Agent] = []
        self._logger = logging.getLogger("simulation")
        self._supervisor = AgentSupervisor(
            restart_limit=scenario.runtime.restart_limit,
            restart_delay=scenario.runtime.restart_delay,
        )
        self._controller = ClassroomController(
            ClassControllerConfig(
                lecture_ticks=scenario.class_controller.lecture_ticks,
                question_ticks=scenario.class_controller.question_ticks,
                group_ticks=scenario.class_controller.group_ticks,
                summary_ticks=scenario.class_controller.summary_ticks,
            )
        )
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop_event = asyncio.Event()
        self._start_tick = max(1, int(start_tick))
        self._end_tick = self._start_tick + int(scenario.ticks) - 1
        self._current_tick = 0
        self._started_at: Optional[float] = None
        self._finished = False
        self._llm_factory = llm_factory
        self._tool_registry = tool_registry
        self._clock = None
        self._schedule = None
        self._sim_time = None
        self._day_index = None
        self._daily_concepts = {}
        self._day_info = {}
        self._rng_seed = int(getattr(scenario, "rng_seed", 42))
        self._sim_rng = random.Random(self._rng_seed)
        self._student_groups = sorted(
            {
                spec.profile.group
                for spec in scenario.agent_specs
                if spec.profile.role == AgentRole.STUDENT
            }
        )
        self._social_graph = None
        if getattr(scenario, "social_graph", None):
            self._social_graph = build_social_graph(
                scenario.social_graph, [spec.profile.agent_id for spec in scenario.agent_specs]
            )
        if scenario.calendar:
            self._clock = SimClock(scenario.calendar)
            if scenario.timetable and scenario.routine and scenario.academic_calendar:
                timetable = Timetable(self._clock, scenario.timetable)
                routine = DailyRoutine(
                    self._clock, scenario.routine, scenario.calendar.weekdays
                )
                curriculum = build_curriculum(scenario.curriculum)
                calendar = build_academic_calendar(scenario.academic_calendar)
                week_patterns = [
                    WeekPattern(
                        name=pattern.name,
                        label=pattern.label,
                        mode=pattern.mode,
                        extra_events=pattern.extra_events,
                    )
                    for pattern in scenario.week_patterns
                ]
                self._schedule = ScheduleGenerator(
                    self._clock,
                    routine,
                    timetable,
                    calendar,
                    week_patterns,
                    scenario.week_plan,
                    scenario.semester_events,
                    curriculum,
                    self._sim_rng,
                    scenario.calendar.weekdays,
                )
        self._prepare_agents()

    def _prepare_agents(self) -> None:
        for index, spec in enumerate(self._scenario.agent_specs):
            profile = spec.profile
            responder = self._llm_factory.create_responder(
                spec,
                scenario=self._scenario,
                directory=self._directory,
                memory_store=self._memory_store,
                tool_registry=self._tool_registry,
            )
            agent_seed = self._rng_seed + sum(ord(ch) for ch in profile.agent_id) + index
            rng = random.Random(agent_seed)
            social_graph = self._social_graph
            if profile.role == AgentRole.STUDENT:
                behavior = StudentBehavior(
                    responder=responder,
                    question_prob=self._scenario.behavior.student_question_prob,
                    office_hours_prob=self._scenario.behavior.office_hours_question_prob,
                    discuss_prob=self._scenario.behavior.student_discuss_prob,
                    peer_discuss_prob=self._scenario.behavior.peer_discuss_prob,
                    peer_reply_prob=self._scenario.behavior.peer_reply_prob,
                    noise_prob=self._scenario.behavior.student_noise_prob,
                    rng=rng,
                    social_graph=social_graph,
                )
            elif profile.role == AgentRole.TEACHER:
                curriculum = None
                if self._schedule:
                    curriculum = self._schedule.curriculum
                behavior = TeacherBehavior(responder=responder, rng=rng, curriculum=curriculum)
            else:
                continue
            agent = Agent(
                profile=profile,
                bus=self._bus,
                directory=self._directory,
                context=ContextManager(),
                behavior=behavior,
                memory_store=self._memory_store,
                prompt=spec.llm.prompt,
            )
            self._agents.append(agent)
            self._supervisor.add(profile.agent_id, agent)

    async def run(self) -> None:
        self._started_at = time.time()
        supervisor_task = asyncio.create_task(self._supervisor.start())
        await self._bus.wait_for_agents(self._directory.all_agents(), timeout=1.5)
        for offset in range(self._scenario.ticks):
            await self._pause_event.wait()
            if self._stop_event.is_set():
                break
            tick = self._start_tick + offset
            self._current_tick = tick
            await self._dispatch_tick(tick)
            if hasattr(self._memory_store, "set_last_tick"):
                self._memory_store.set_last_tick(tick)
            await asyncio.sleep(self._scenario.tick_seconds)
        await self._shutdown()
        await supervisor_task
        self._memory_store.close()
        self._finished = True

    async def _dispatch_tick(self, tick: int) -> None:
        recipients = self._directory.all_agents()
        await self._bus.emit_system(SystemEvent("tick", {"tick": tick}), recipients)
        if self._clock:
            self._sim_time = self._clock.time_for_tick(tick)
            await self._dispatch_calendar_events(self._sim_time)
        for event in self._scenario.events_for_tick(tick):
            if event.event_type == "announcement":
                await self._broadcast_announcement(event.payload["message"])
            elif event.event_type == "class_session":
                self._controller.register_session(tick, event.payload)
            elif event.event_type in {"student_discuss", "group_discussion"}:
                group = event.payload.get("group", "all")
                recipients = self._directory.group_members(group, role=AgentRole.STUDENT)
                await self._bus.emit_system(
                    SystemEvent(event.event_type, event.payload), recipients
                )
            else:
                teacher_id = event.payload["teacher_id"]
                await self._bus.emit_system(
                    SystemEvent(event.event_type, event.payload), [teacher_id]
                )
        for event in self._controller.due_events(tick):
            if event.event_type in {"group_discussion"}:
                group = event.payload.get("group", "all")
                recipients = self._directory.group_members(group, role=AgentRole.STUDENT)
                await self._bus.emit_system(event, recipients)
            elif event.event_type == "phase_questions":
                group = event.payload.get("group", "all")
                recipients = self._directory.group_members(group, role=AgentRole.STUDENT)
                await self._bus.emit_system(event, recipients)
            else:
                teacher_id = event.payload["teacher_id"]
                await self._bus.emit_system(event, [teacher_id])

    async def _dispatch_calendar_events(self, sim_time) -> None:
        if not self._schedule:
            return
        if self._day_index is None or sim_time.day_index != self._day_index:
            self._day_index = sim_time.day_index
            self._daily_concepts.setdefault(sim_time.day_index, {})
            await self._bus.emit_system(
                SystemEvent("day_transition", {"day_index": sim_time.day_index}),
                self._directory.group_members("all", role=AgentRole.STUDENT),
            )
        day_info = self._schedule.day_info(sim_time)
        self._day_info = day_info
        for event in self._schedule.events_for_time(sim_time):
            if event.event_type == "class_session":
                self._controller.register_session(sim_time.tick, event.payload)
                self._record_concepts(
                    sim_time.day_index,
                    event.payload.get("group", "all"),
                    event.payload.get("concepts", []),
                )
            elif event.event_type == "review":
                await self._dispatch_review(sim_time, event.payload)
            elif event.event_type in {"announcement", "activity"}:
                await self._broadcast_announcement(event.payload.get("message", ""))
                await self._bus.emit_system(
                    SystemEvent(
                        "routine",
                        {
                            "action": event.payload.get("action", event.payload.get("activity", "")),
                            "clock_time": sim_time.clock_time,
                            "weekday": sim_time.weekday_cn,
                            "date": day_info.get("date"),
                        },
                    ),
                    self._directory.group_members("all", role=AgentRole.STUDENT),
                )
        if self._schedule and self._schedule.is_test_start(sim_time):
            await self._dispatch_daily_test(sim_time)

    async def _dispatch_review(self, sim_time, payload: dict) -> None:
        for group in self._student_groups:
            concepts = self._recent_concepts(sim_time.day_index, group, limit=3)
            if not concepts:
                continue
            review_payload = dict(payload)
            review_payload.update(
                {
                    "group": group,
                    "topics": concepts,
                }
            )
            recipients = self._directory.group_members(group, role=AgentRole.STUDENT)
            await self._bus.emit_system(SystemEvent("review", review_payload), recipients)

    async def _dispatch_daily_test(self, sim_time) -> None:
        prev_day = sim_time.day_index - 1
        topics_by_group = self._daily_concepts.get(prev_day, {})
        for group in self._student_groups:
            concepts = topics_by_group.get(group, [])
            if not concepts:
                continue
            teachers = self._directory.group_members(group, role=AgentRole.TEACHER)
            if not teachers:
                continue
            payload = {
                "group": group,
                "concepts": concepts,
                "weekday": sim_time.weekday_cn,
                "clock_time": sim_time.clock_time,
            }
            await self._bus.emit_system(
                SystemEvent("daily_test", payload), [teachers[0]]
            )

    def _record_concepts(self, day_index: int, group: str, concepts: list[str]) -> None:
        if not concepts:
            return
        day_topics = self._daily_concepts.setdefault(day_index, {})
        stored = day_topics.setdefault(group, [])
        for concept in concepts:
            if concept not in stored:
                stored.append(concept)

    def _recent_concepts(self, day_index: int, group: str, limit: int) -> list[str]:
        topics = []
        day_topics = self._daily_concepts.get(day_index, {}).get(group, [])
        topics.extend(day_topics)
        if len(topics) < limit:
            prev_topics = self._daily_concepts.get(day_index - 1, {}).get(group, [])
            topics = prev_topics + topics
        return topics[-limit:]

    async def _broadcast_announcement(self, message: str) -> None:
        recipients = self._directory.all_agents()
        outbound = Message(
            sender_id="system",
            receiver_id=None,
            topic="announcement",
            content=message,
            timestamp=time.time(),
        )
        await self._bus.broadcast(outbound, recipients)
        self._logger.info("announcement: %s", message)

    async def _shutdown(self) -> None:
        recipients = self._directory.all_agents()
        await self._bus.emit_system(SystemEvent("shutdown", {}), recipients)

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()

    def status(self) -> dict:
        sim_time = None
        if self._sim_time:
            sim_time = {
                "weekday": self._sim_time.weekday_cn,
                "clock_time": self._sim_time.clock_time,
                "day_index": self._sim_time.day_index,
            }
            sim_time.update(self._day_info or {})
        return {
            "current_tick": self._current_tick,
            "running": self._started_at is not None
            and not self._finished
            and not self._stop_event.is_set(),
            "paused": not self._pause_event.is_set(),
            "agent_count": len(self._agents),
            "ticks_total": self._end_tick,
            "sim_time": sim_time,
        }
