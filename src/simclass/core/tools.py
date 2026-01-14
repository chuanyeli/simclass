from __future__ import annotations

import time
from typing import List

from simclass.core.llm.tooling import ToolRegistry, ToolSpec, ToolContext


def build_default_tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="get_time",
            description="获取当前UTC时间。",
            input_schema={},
            handler=_tool_get_time,
        )
    )
    registry.register(
        ToolSpec(
            name="get_schedule",
            description="获取某个分组的后续日程。",
            input_schema={"group": "string"},
            handler=_tool_get_schedule,
        )
    )
    registry.register(
        ToolSpec(
            name="get_recent_memory",
            description="获取该角色最近的记忆片段。",
            input_schema={"limit": "number"},
            handler=_tool_get_recent_memory,
        )
    )
    return registry


def _tool_get_time(args: dict, context: ToolContext) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _tool_get_schedule(args: dict, context: ToolContext) -> str:
    group = args.get("group")
    if not group and context.directory:
        profile = context.directory.get_profile(context.agent_id)
        if profile:
            group = profile.group
    if not group:
        return "no group provided"
    timetable = getattr(context.scenario, "timetable", [])
    if timetable:
        items = []
        for entry in timetable:
            if entry.group not in (group, "all") and group != "all":
                continue
            weekdays = ",".join(entry.weekdays)
            items.append(
                f"{weekdays} {entry.start_time} {entry.topic}".strip()
            )
        return "; ".join(items) if items else "no upcoming classes"
    events = []
    for event in getattr(context.scenario, "events", []):
        payload = getattr(event, "payload", {})
        if payload.get("group") in (group, "all") or group == "all":
            events.append(
                f"tick {event.tick}: {event.event_type} {payload.get('topic', '')}".strip()
            )
    return "; ".join(events) if events else "no upcoming events"


def _tool_get_recent_memory(args: dict, context: ToolContext) -> str:
    limit = int(args.get("limit", 5))
    if not context.memory_store:
        return "memory store unavailable"
    records = context.memory_store.load_recent_memory(context.agent_id, limit=limit)
    summaries: List[str] = []
    for record in reversed(records):
        summaries.append(f"{record.kind}:{record.content}")
    return " | ".join(summaries) if summaries else "no memory"
