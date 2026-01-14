from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from simclass.domain import AgentProfile, AgentRole


class AgentDirectory:
    def __init__(self, profiles: Iterable[AgentProfile]) -> None:
        self._profiles: Dict[str, AgentProfile] = {}
        self._groups: Dict[str, List[str]] = {}
        for profile in profiles:
            self._profiles[profile.agent_id] = profile
            self._groups.setdefault(profile.group, []).append(profile.agent_id)
        self._groups["all"] = list(self._profiles.keys())

    def all_agents(self) -> List[str]:
        return list(self._profiles.keys())

    def get_profile(self, agent_id: str) -> Optional[AgentProfile]:
        return self._profiles.get(agent_id)

    def group_members(self, group: str, role: Optional[AgentRole] = None) -> List[str]:
        members = self._groups.get(group, [])
        if role is None:
            return list(members)
        return [
            agent_id
            for agent_id in members
            if self._profiles[agent_id].role == role
        ]
