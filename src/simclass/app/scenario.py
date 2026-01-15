from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from simclass.domain import AgentProfile, AgentRole


@dataclass(frozen=True)
class RuntimeConfig:
    queue_maxsize: int
    send_timeout: float
    send_retries: int
    retry_backoff: float
    restart_limit: int
    restart_delay: float


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    provider: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    retry_count: int
    retry_backoff: float


@dataclass(frozen=True)
class AgentLLMConfig:
    enabled: bool
    provider: str
    model: str
    tools: List[str]
    prompt: str


@dataclass(frozen=True)
class AgentSpec:
    profile: AgentProfile
    llm: AgentLLMConfig


@dataclass(frozen=True)
class BehaviorConfig:
    student_question_prob: float
    office_hours_question_prob: float
    student_discuss_prob: float
    peer_discuss_prob: float
    peer_reply_prob: float
    student_noise_prob: float


@dataclass(frozen=True)
class ApiConfig:
    host: str
    port: int


@dataclass(frozen=True)
class ClassControllerConfig:
    lecture_ticks: int
    question_ticks: int
    group_ticks: int
    summary_ticks: int


@dataclass(frozen=True)
class CalendarConfig:
    start_day: str
    start_time: str
    minutes_per_tick: float
    day_minutes: int
    weekdays: List[str]


@dataclass(frozen=True)
class RoutineConfig:
    wake_time: str
    breakfast_start: str
    breakfast_end: str
    morning_class_start: str
    morning_class_count: int
    class_duration: int
    break_duration: int
    test_start: str
    test_end: str
    lunch_start: str
    lunch_end: str
    afternoon_class_start: str
    afternoon_class_count: int
    school_end: str
    review_breaks: bool
    review_after_school: bool
    after_school_review_offset: int


@dataclass(frozen=True)
class TimetableEntry:
    group: str
    teacher_id: str
    topic: str
    course_id: str
    lesson_plan: str
    start_time: str
    duration: int
    weekdays: List[str]


@dataclass(frozen=True)
class AcademicCalendarConfig:
    start_date: str
    weeks: int
    holidays: List[str]
    makeup_days: List[str]
    exam_weeks: List[int]
    review_weeks: List[int]


@dataclass(frozen=True)
class WeekPatternConfig:
    name: str
    label: str
    mode: str
    extra_events: List[dict]


@dataclass(frozen=True)
class CurriculumConfig:
    courses: List[dict]
    concepts: List[dict]
    lesson_plans: dict
    question_bank: dict


@dataclass(frozen=True)
class ScenarioEvent:
    tick: int
    event_type: str
    payload: dict


@dataclass(frozen=True)
class Scenario:
    agent_specs: List[AgentSpec]
    ticks: int
    tick_seconds: float
    events: List[ScenarioEvent]
    runtime: RuntimeConfig
    llm: LLMConfig
    api: ApiConfig
    behavior: BehaviorConfig
    persona_templates: dict
    class_controller: ClassControllerConfig
    calendar: Optional[CalendarConfig]
    routine: Optional[RoutineConfig]
    timetable: List[TimetableEntry]
    academic_calendar: Optional[AcademicCalendarConfig]
    week_patterns: List[WeekPatternConfig]
    week_plan: List[str]
    semester_events: List[dict]
    scenes: List[dict]
    classroom_layout: dict
    objects: List[dict]
    curriculum: Optional[CurriculumConfig]
    rng_seed: int
    social_graph: dict
    perception: dict

    def events_for_tick(self, tick: int) -> List[ScenarioEvent]:
        return [event for event in self.events if event.tick == tick]


def load_scenario(path: Path) -> Scenario:
    with path.open("r", encoding="utf-8-sig") as handle:
        raw = json.load(handle)

    simulation_cfg = raw["simulation"]
    runtime_cfg = raw.get("runtime", {})
    llm_cfg = raw.get("llm", {})
    api_cfg = raw.get("api", {})
    behavior_cfg = raw.get("behavior", {})
    persona_templates = raw.get("persona_templates", {})
    controller_cfg = raw.get("class_controller", {})
    calendar_cfg = raw.get("calendar")
    routine_cfg = raw.get("routine")
    timetable_cfg = raw.get("timetable", [])
    academic_cfg = raw.get("academic_calendar")
    week_patterns_cfg = raw.get("week_patterns", {})
    week_plan_cfg = raw.get("week_plan", [])
    semester_events_cfg = raw.get("semester_events", [])
    scenes_cfg = raw.get("scenes", [])
    classroom_layout_cfg = raw.get("classroom_layout", {})
    objects_cfg = raw.get("objects", [])
    curriculum_cfg = raw.get("curriculum")
    lesson_plans_cfg = raw.get("lesson_plans", {})
    question_bank_cfg = raw.get("question_bank", {})
    social_graph_cfg = raw.get("social_graph", {})
    perception_cfg = raw.get("perception", {})
    prompts = raw.get("prompts", {})
    agent_defaults = raw.get("agent_defaults", {})
    default_agent_llm = agent_defaults.get("llm", {})
    default_tools = default_agent_llm.get("tools", [])
    default_persona = agent_defaults.get("persona", {})

    agent_specs: List[AgentSpec] = []
    for item in raw["agents"]:
        persona = item.get("persona", {}) or {}
        default_traits = default_persona.get("traits", [])
        default_interests = default_persona.get("interests", [])
        traits = persona.get("traits", default_traits)
        interests = persona.get("interests", default_interests)
        merged_persona = {
            "traits": list(traits) if isinstance(traits, list) else [str(traits)],
            "tone": persona.get("tone", default_persona.get("tone", "")),
            "interests": list(interests)
            if isinstance(interests, list)
            else [str(interests)],
            "bio": persona.get("bio", default_persona.get("bio", "")),
            "engagement": float(persona.get("engagement", default_persona.get("engagement", 0.6))),
            "confidence": float(persona.get("confidence", default_persona.get("confidence", 0.6))),
            "collaboration": float(
                persona.get("collaboration", default_persona.get("collaboration", 0.6))
            ),
        }
        for key, value in persona.items():
            if key not in merged_persona:
                merged_persona[key] = value
        profile = AgentProfile(
            agent_id=item["id"],
            name=item["name"],
            role=AgentRole(item["role"]),
            group=item["group"],
            persona=merged_persona,
        )
        agent_llm = item.get("llm", {})
        role_key = profile.role.value
        prompt = agent_llm.get("prompt", prompts.get(role_key, ""))
        llm = AgentLLMConfig(
            enabled=bool(agent_llm.get("enabled", llm_cfg.get("enabled", False))),
            provider=str(agent_llm.get("provider", llm_cfg.get("provider", "deepseek"))),
            model=str(agent_llm.get("model", llm_cfg.get("model", "deepseek-chat"))),
            tools=list(agent_llm.get("tools", default_tools)),
            prompt=prompt,
        )
        agent_specs.append(AgentSpec(profile=profile, llm=llm))

    events = []
    for item in raw.get("schedule", []):
        payload = dict(item)
        payload.pop("tick", None)
        payload.pop("type", None)
        events.append(
            ScenarioEvent(
                tick=item["tick"],
                event_type=item["type"],
                payload=payload,
            )
        )
    runtime = RuntimeConfig(
        queue_maxsize=int(runtime_cfg.get("queue_maxsize", 100)),
        send_timeout=float(runtime_cfg.get("send_timeout", 0.2)),
        send_retries=int(runtime_cfg.get("send_retries", 2)),
        retry_backoff=float(runtime_cfg.get("retry_backoff", 0.2)),
        restart_limit=int(runtime_cfg.get("restart_limit", 2)),
        restart_delay=float(runtime_cfg.get("restart_delay", 0.2)),
    )
    llm = LLMConfig(
        enabled=bool(llm_cfg.get("enabled", False)),
        provider=str(llm_cfg.get("provider", "deepseek")),
        base_url=str(llm_cfg.get("base_url", "https://api.deepseek.com/v1")),
        model=str(llm_cfg.get("model", "deepseek-chat")),
        temperature=float(llm_cfg.get("temperature", 0.3)),
        max_tokens=int(llm_cfg.get("max_tokens", 200)),
        timeout_seconds=float(llm_cfg.get("timeout_seconds", 15)),
        retry_count=int(llm_cfg.get("retry_count", 2)),
        retry_backoff=float(llm_cfg.get("retry_backoff", 0.5)),
    )
    api = ApiConfig(
        host=str(api_cfg.get("host", "127.0.0.1")),
        port=int(api_cfg.get("port", 8010)),
    )
    behavior = BehaviorConfig(
        student_question_prob=float(behavior_cfg.get("student_question_prob", 0.7)),
        office_hours_question_prob=float(
            behavior_cfg.get("office_hours_question_prob", 0.7)
        ),
        student_discuss_prob=float(behavior_cfg.get("student_discuss_prob", 0.5)),
        peer_discuss_prob=float(behavior_cfg.get("peer_discuss_prob", 0.6)),
        peer_reply_prob=float(behavior_cfg.get("peer_reply_prob", 0.5)),
        student_noise_prob=float(behavior_cfg.get("student_noise_prob", 0.08)),
    )
    class_controller = ClassControllerConfig(
        lecture_ticks=int(controller_cfg.get("lecture_ticks", 1)),
        question_ticks=int(controller_cfg.get("question_ticks", 1)),
        group_ticks=int(controller_cfg.get("group_ticks", 1)),
        summary_ticks=int(controller_cfg.get("summary_ticks", 1)),
    )
    calendar = None
    if calendar_cfg:
        calendar = CalendarConfig(
            start_day=str(calendar_cfg.get("start_day", "Mon")),
            start_time=str(calendar_cfg.get("start_time", "12:00")),
            minutes_per_tick=float(calendar_cfg.get("minutes_per_tick", 1.0)),
            day_minutes=int(calendar_cfg.get("day_minutes", 240)),
            weekdays=list(calendar_cfg.get("weekdays", ["Mon", "Tue", "Wed", "Thu", "Fri"])),
        )
    routine = None
    if routine_cfg:
        routine = RoutineConfig(
            wake_time=str(routine_cfg.get("wake_time", "08:00")),
            breakfast_start=str(routine_cfg.get("breakfast_start", "08:20")),
            breakfast_end=str(routine_cfg.get("breakfast_end", "08:40")),
            morning_class_start=str(routine_cfg.get("morning_class_start", "08:50")),
            morning_class_count=int(routine_cfg.get("morning_class_count", 3)),
            class_duration=int(routine_cfg.get("class_duration", 40)),
            break_duration=int(routine_cfg.get("break_duration", 10)),
            test_start=str(routine_cfg.get("test_start", "11:20")),
            test_end=str(routine_cfg.get("test_end", "12:00")),
            lunch_start=str(routine_cfg.get("lunch_start", "12:00")),
            lunch_end=str(routine_cfg.get("lunch_end", "14:00")),
            afternoon_class_start=str(routine_cfg.get("afternoon_class_start", "14:00")),
            afternoon_class_count=int(routine_cfg.get("afternoon_class_count", 5)),
            school_end=str(routine_cfg.get("school_end", "18:00")),
            review_breaks=bool(routine_cfg.get("review_breaks", True)),
            review_after_school=bool(routine_cfg.get("review_after_school", True)),
            after_school_review_offset=int(
                routine_cfg.get("after_school_review_offset", 10)
            ),
        )
    timetable: List[TimetableEntry] = []
    for entry in timetable_cfg:
        timetable.append(
            TimetableEntry(
                group=str(entry.get("group", "all")),
                teacher_id=str(entry.get("teacher_id", "")),
                topic=str(entry.get("topic", "")),
                course_id=str(entry.get("course_id", entry.get("topic", ""))),
                lesson_plan=str(entry.get("lesson_plan", "")),
                start_time=str(entry.get("start_time", "08:50")),
                duration=int(entry.get("duration", 40)),
                weekdays=list(entry.get("weekdays", ["Mon", "Tue", "Wed", "Thu", "Fri"])),
            )
        )
    academic_calendar = None
    if academic_cfg:
        academic_calendar = AcademicCalendarConfig(
            start_date=str(academic_cfg.get("start_date", "2026-01-13")),
            weeks=int(academic_cfg.get("weeks", 16)),
            holidays=list(academic_cfg.get("holidays", [])),
            makeup_days=list(academic_cfg.get("makeup_days", [])),
            exam_weeks=list(academic_cfg.get("exam_weeks", [])),
            review_weeks=list(academic_cfg.get("review_weeks", [])),
        )
    week_patterns: List[WeekPatternConfig] = []
    for name, cfg in week_patterns_cfg.items():
        week_patterns.append(
            WeekPatternConfig(
                name=name,
                label=str(cfg.get("label", name)),
                mode=str(cfg.get("mode", "normal")),
                extra_events=list(cfg.get("extra_events", [])),
            )
        )
    curriculum = None
    if curriculum_cfg:
        curriculum = CurriculumConfig(
            courses=list(curriculum_cfg.get("courses", [])),
            concepts=list(curriculum_cfg.get("concepts", [])),
            lesson_plans=dict(lesson_plans_cfg),
            question_bank=dict(question_bank_cfg),
        )
    return Scenario(
        agent_specs=agent_specs,
        ticks=int(simulation_cfg["ticks"]),
        tick_seconds=float(simulation_cfg["tick_seconds"]),
        events=events,
        runtime=runtime,
        llm=llm,
        api=api,
        behavior=behavior,
        persona_templates=persona_templates,
        class_controller=class_controller,
        calendar=calendar,
        routine=routine,
        timetable=timetable,
        academic_calendar=academic_calendar,
        week_patterns=week_patterns,
        week_plan=list(week_plan_cfg),
        semester_events=list(semester_events_cfg),
        scenes=list(scenes_cfg),
        classroom_layout=dict(classroom_layout_cfg),
        objects=list(objects_cfg),
        curriculum=curriculum,
        rng_seed=int(raw.get("rng_seed", 42)),
        social_graph=dict(social_graph_cfg),
        perception=dict(perception_cfg),
    )
