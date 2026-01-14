from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from simclass.core.agent import Agent
from simclass.core.behavior import StudentBehavior, TeacherBehavior
from simclass.core.bus import AsyncMessageBus
from simclass.core.calendar import DailyRoutine, SimClock, Timetable
from simclass.core.context import ContextManager
from simclass.core.controller import ClassroomController, ClassControllerConfig
from simclass.core.directory import AgentDirectory
from simclass.core.supervisor import AgentSupervisor
from simclass.domain import AgentRole, Message, SystemEvent


class Simulation:
    def __init__(self, scenario, memory_store, llm_factory, tool_registry) -> None:
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
        self._current_tick = 0
        self._started_at: Optional[float] = None
        self._finished = False
        self._llm_factory = llm_factory
        self._tool_registry = tool_registry
        self._clock = None
        self._timetable = None
        self._routine = None
        self._sim_time = None
        self._day_index = None
        self._daily_topics = {}
        self._student_groups = sorted(
            {
                spec.profile.group
                for spec in scenario.agent_specs
                if spec.profile.role == AgentRole.STUDENT
            }
        )
        if scenario.calendar:
            self._clock = SimClock(scenario.calendar)
            if scenario.timetable:
                self._timetable = Timetable(self._clock, scenario.timetable)
            if scenario.routine:
                self._routine = DailyRoutine(
                    self._clock, scenario.routine, scenario.calendar.weekdays
                )
        self._prepare_agents()

    def _prepare_agents(self) -> None:
        for spec in self._scenario.agent_specs:
            profile = spec.profile
            responder = self._llm_factory.create_responder(
                spec,
                scenario=self._scenario,
                directory=self._directory,
                memory_store=self._memory_store,
                tool_registry=self._tool_registry,
            )
            if profile.role == AgentRole.STUDENT:
                behavior = StudentBehavior(
                    responder=responder,
                    question_prob=self._scenario.behavior.student_question_prob,
                    office_hours_prob=self._scenario.behavior.office_hours_question_prob,
                    discuss_prob=self._scenario.behavior.student_discuss_prob,
                    peer_discuss_prob=self._scenario.behavior.peer_discuss_prob,
                    peer_reply_prob=self._scenario.behavior.peer_reply_prob,
                )
            elif profile.role == AgentRole.TEACHER:
                behavior = TeacherBehavior(responder=responder)
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
        for tick in range(1, self._scenario.ticks + 1):
            await self._pause_event.wait()
            if self._stop_event.is_set():
                break
            self._current_tick = tick
            await self._dispatch_tick(tick)
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
        if self._day_index is None or sim_time.day_index != self._day_index:
            self._day_index = sim_time.day_index
            self._daily_topics.setdefault(sim_time.day_index, {})
        if self._timetable:
            entries = self._timetable.entries_for(sim_time.weekday, sim_time.sim_minute)
            for entry in entries:
                payload = {
                    "teacher_id": entry.teacher_id,
                    "group": entry.group,
                    "topic": entry.topic,
                    "lesson_plan": entry.lesson_plan,
                    "weekday": sim_time.weekday_cn,
                    "clock_time": sim_time.clock_time,
                }
                self._controller.register_session(sim_time.tick, payload)
                self._record_topic(sim_time.day_index, entry.group, entry.topic)
        if self._routine:
            actions = self._routine.actions_for(sim_time.weekday, sim_time.sim_minute)
            for action in actions:
                await self._handle_routine_action(sim_time, action)
            if self._routine.is_test_start(sim_time.sim_minute, sim_time.weekday):
                await self._dispatch_daily_test(sim_time)

    async def _handle_routine_action(self, sim_time, action: str) -> None:
        if action == "review_break":
            await self._dispatch_review(sim_time, reason="课间回顾", limit=1)
            return
        if action == "review_home":
            await self._dispatch_review(sim_time, reason="放学回顾", limit=3)
            return
        label_map = {
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
        label = label_map.get(action)
        if label:
            await self._broadcast_announcement(
                f"{sim_time.weekday_cn} {sim_time.clock_time} · {label}"
            )

    async def _dispatch_review(self, sim_time, reason: str, limit: int) -> None:
        for group in self._student_groups:
            topics = self._recent_topics(sim_time.day_index, group, limit)
            if not topics:
                continue
            payload = {
                "group": group,
                "topics": topics,
                "reason": reason,
                "weekday": sim_time.weekday_cn,
                "clock_time": sim_time.clock_time,
            }
            recipients = self._directory.group_members(group, role=AgentRole.STUDENT)
            await self._bus.emit_system(SystemEvent("review", payload), recipients)

    async def _dispatch_daily_test(self, sim_time) -> None:
        prev_day = sim_time.day_index - 1
        topics_by_group = self._daily_topics.get(prev_day, {})
        for group in self._student_groups:
            topics = topics_by_group.get(group, [])
            if not topics:
                continue
            teachers = self._directory.group_members(group, role=AgentRole.TEACHER)
            if not teachers:
                continue
            payload = {
                "group": group,
                "topics": topics,
                "weekday": sim_time.weekday_cn,
                "clock_time": sim_time.clock_time,
            }
            await self._bus.emit_system(
                SystemEvent("daily_test", payload), [teachers[0]]
            )

    def _record_topic(self, day_index: int, group: str, topic: str) -> None:
        if not topic:
            return
        day_topics = self._daily_topics.setdefault(day_index, {})
        topics = day_topics.setdefault(group, [])
        if topic not in topics:
            topics.append(topic)

    def _recent_topics(self, day_index: int, group: str, limit: int) -> list[str]:
        topics = []
        day_topics = self._daily_topics.get(day_index, {}).get(group, [])
        topics.extend(day_topics)
        if len(topics) < limit:
            prev_topics = self._daily_topics.get(day_index - 1, {}).get(group, [])
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
        return {
            "current_tick": self._current_tick,
            "ticks_total": self._scenario.ticks,
            "running": self._started_at is not None
            and not self._finished
            and not self._stop_event.is_set(),
            "paused": not self._pause_event.is_set(),
            "agent_count": len(self._agents),
            "sim_time": sim_time,
        }
