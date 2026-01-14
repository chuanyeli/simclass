from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class SocialGraph:
    friends: Dict[str, List[str]]
    conflicts: Dict[str, List[str]]
    seatmates: Dict[str, List[str]]

    def choose_peer(self, rng, agent_id: str, candidates: List[str]) -> str:
        weights = []
        for candidate in candidates:
            weight = 1.0
            if candidate in self.friends.get(agent_id, []):
                weight += 1.0
            if candidate in self.seatmates.get(agent_id, []):
                weight += 0.5
            if candidate in self.conflicts.get(agent_id, []):
                weight *= 0.4
            weights.append(weight)
        return _weighted_choice(rng, candidates, weights)


def build_social_graph(cfg: dict, agent_ids: Iterable[str]) -> SocialGraph:
    friends = _build_map(cfg.get("friends", []), agent_ids)
    conflicts = _build_map(cfg.get("conflicts", []), agent_ids)
    seatmates = _build_map(cfg.get("seatmates", []), agent_ids)
    return SocialGraph(friends=friends, conflicts=conflicts, seatmates=seatmates)


def _build_map(pairs: Iterable[Tuple[str, str]], agent_ids: Iterable[str]) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {agent_id: [] for agent_id in agent_ids}
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        a, b = pair
        if a not in mapping or b not in mapping:
            continue
        mapping[a].append(b)
        mapping[b].append(a)
    return mapping


def _weighted_choice(rng, options: List[str], weights: List[float]) -> str:
    if not options:
        return ""
    total = sum(weights)
    if total <= 0:
        return rng.choice(options) if rng else options[0]
    threshold = (rng.random() if rng else 0.5) * total
    cumulative = 0.0
    for option, weight in zip(options, weights):
        cumulative += weight
        if cumulative >= threshold:
            return option
    return options[-1]
