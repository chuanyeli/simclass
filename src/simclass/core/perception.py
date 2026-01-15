from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Optional

from simclass.domain import AgentRole, Message


@dataclass(frozen=True)
class PerceptionProfile:
    vision_range: float = 5.0
    hearing_range: float = 6.0
    distance_decay: str = "linear"
    decay_alpha: float = 0.6
    occluded_seats: list[str] = field(default_factory=list)
    occlusion_factor: float = 0.5


@dataclass(frozen=True)
class PerceptionConfig:
    enabled: bool
    topic_channels: Dict[str, str]
    bypass_topics: set[str]
    suspicion_topics: set[str]
    mask_sender_topics: set[str]
    observer_topics: set[str]
    log_observers: bool
    observer_delivery: bool
    observer_roles: set[AgentRole]
    observer_topic: str
    observer_chance: float
    degrade_threshold: float
    default_profile: PerceptionProfile
    teacher_profile: Optional[PerceptionProfile]
    student_profile: Optional[PerceptionProfile]


@dataclass(frozen=True)
class PerceptionResult:
    perceived: bool
    probability: float
    distance: Optional[int]
    channel: str
    masked: bool
    suspect_row: Optional[int]
    suspicion_score: Optional[float]


def compute_probability(
    distance: Optional[int],
    range_value: float,
    decay_mode: str,
    decay_alpha: float,
) -> float:
    if distance is None:
        return 1.0
    if range_value <= 0:
        return 0.0
    if decay_mode == "exponential":
        return math.exp(-decay_alpha * float(distance))
    return max(0.0, 1.0 - float(distance) / float(range_value))


def _profile_from_cfg(cfg: dict) -> PerceptionProfile:
    return PerceptionProfile(
        vision_range=float(cfg.get("vision_range", 5.0)),
        hearing_range=float(cfg.get("hearing_range", 6.0)),
        distance_decay=str(cfg.get("distance_decay", "linear")),
        decay_alpha=float(cfg.get("decay_alpha", 0.6)),
        occluded_seats=list(cfg.get("occluded_seats", [])),
        occlusion_factor=float(cfg.get("occlusion_factor", 0.5)),
    )


def _observer_roles(roles_cfg) -> set[AgentRole]:
    if not roles_cfg:
        return {AgentRole.TEACHER}
    roles = set()
    for item in roles_cfg:
        try:
            roles.add(AgentRole(item))
        except ValueError:
            continue
    return roles or {AgentRole.TEACHER}


def build_perception_config(cfg: Optional[dict]) -> PerceptionConfig:
    if not cfg:
        return PerceptionConfig(
            enabled=False,
            topic_channels={},
            bypass_topics=set(),
            suspicion_topics=set(),
            mask_sender_topics=set(),
            observer_topics=set(),
            log_observers=False,
            observer_delivery=False,
            observer_roles={AgentRole.TEACHER},
            observer_topic="overheard",
            observer_chance=0.4,
            degrade_threshold=0.35,
            default_profile=PerceptionProfile(),
            teacher_profile=None,
            student_profile=None,
        )
    default_profile = _profile_from_cfg(cfg.get("default_profile", {}))
    teacher_profile = (
        _profile_from_cfg(cfg.get("teacher_profile", {}))
        if cfg.get("teacher_profile")
        else None
    )
    student_profile = (
        _profile_from_cfg(cfg.get("student_profile", {}))
        if cfg.get("student_profile")
        else None
    )
    observer_cfg = cfg.get("observer_delivery", {})
    if isinstance(observer_cfg, bool):
        observer_enabled = observer_cfg
        observer_roles = _observer_roles(["teacher"])
        observer_topic = "overheard"
        observer_chance = 0.4
    else:
        observer_enabled = bool(observer_cfg.get("enabled", False))
        observer_roles = _observer_roles(observer_cfg.get("roles", ["teacher"]))
        observer_topic = str(observer_cfg.get("topic", "overheard"))
        observer_chance = float(observer_cfg.get("chance", 0.4))
    return PerceptionConfig(
        enabled=bool(cfg.get("enabled", True)),
        topic_channels=dict(cfg.get("topic_channels", {})),
        bypass_topics=set(cfg.get("bypass_topics", [])),
        suspicion_topics=set(cfg.get("suspicion_topics", [])),
        mask_sender_topics=set(cfg.get("mask_sender_topics", [])),
        observer_topics=set(cfg.get("observer_topics", [])),
        log_observers=bool(cfg.get("log_observers", False)),
        observer_delivery=observer_enabled,
        observer_roles=observer_roles,
        observer_topic=observer_topic,
        observer_chance=observer_chance,
        degrade_threshold=float(cfg.get("degrade_threshold", 0.35)),
        default_profile=default_profile,
        teacher_profile=teacher_profile,
        student_profile=student_profile,
    )


class PerceptionEngine:
    def __init__(
        self,
        world,
        directory,
        config: PerceptionConfig,
        rng: Optional[random.Random] = None,
        record_event=None,
    ) -> None:
        self._world = world
        self._directory = directory
        self._config = config
        self._rng = rng or random.Random()
        self._record_event = record_event

    def filter_message(self, message: Message, receiver_id: Optional[str]) -> Optional[Message]:
        if not receiver_id or not self._config.enabled:
            return message
        if message.topic in self._config.bypass_topics:
            self._log_true(message, receiver_id, 1.0, None, "bypass")
            self._log_perceived(message, receiver_id, 1.0, None, "bypass")
            return message
        result = self.evaluate(message, receiver_id)
        self._log_true(message, receiver_id, result.probability, result.distance, result.channel)
        perceived_message = self.perceive(message, receiver_id, result=result)
        if perceived_message is None:
            return None
        self._log_perceived(message, receiver_id, result.probability, result.distance, result.channel)
        if result.suspicion_score is not None:
            self._log_suspicion(receiver_id, result.suspicion_score, result.suspect_row)
        if self._config.log_observers and message.topic in self._config.observer_topics:
            self._log_observer_perception(message, receiver_id)
        return perceived_message

    def perceive(
        self, message: Message, receiver_id: str, result: Optional[PerceptionResult] = None
    ) -> Optional[Message]:
        if not self._config.enabled:
            return message
        if result is None:
            result = self.evaluate(message, receiver_id)
        if not result.perceived:
            return None
        return self._build_perceived_message(message, receiver_id, result)

    def observer_messages(self, message: Message, receiver_id: Optional[str]) -> list[Message]:
        if not self._config.enabled or not self._config.observer_delivery:
            return []
        if message.topic not in self._config.observer_topics:
            return []
        if not self._directory:
            return []
        observers: list[Message] = []
        for agent_id in self._directory.all_agents():
            if agent_id in {message.sender_id, receiver_id}:
                continue
            role = self._role_for(agent_id)
            if role and role not in self._config.observer_roles:
                continue
            result = self.evaluate(message, agent_id)
            if not result.perceived:
                continue
            if self._rng.random() > self._config.observer_chance:
                continue
            sender_id = message.sender_id
            content = message.content
            if result.probability < self._config.degrade_threshold:
                sender_id = "unknown"
                content = self._degrade_content(content)
            observed = Message(
                sender_id=sender_id,
                receiver_id=agent_id,
                topic=self._config.observer_topic,
                content=f"from={sender_id};topic={message.topic};content={content}",
                timestamp=message.timestamp,
            )
            observers.append(observed)
        return observers

    def evaluate(self, message: Message, receiver_id: str) -> PerceptionResult:
        receiver_profile = self._profile_for(receiver_id)
        channel = self._config.topic_channels.get(message.topic, "hearing")
        distance = self._distance_between(message.sender_id, receiver_id)
        range_value = (
            receiver_profile.hearing_range
            if channel == "hearing"
            else receiver_profile.vision_range
        )
        prob = compute_probability(
            distance,
            range_value,
            receiver_profile.distance_decay,
            receiver_profile.decay_alpha,
        )
        if channel == "vision" and self._is_occluded(receiver_profile, message.sender_id):
            prob *= receiver_profile.occlusion_factor
        prob = max(0.0, min(1.0, prob))
        perceived = self._rng.random() <= prob
        masked = False
        suspect_row = None
        suspicion_score = None
        receiver_role = self._role_for(receiver_id)
        if receiver_role == AgentRole.TEACHER and message.topic in self._config.suspicion_topics:
            sender_loc = self._location_for(message.sender_id)
            suspect_row = sender_loc.row if sender_loc else None
            suspicion_score = round(max(0.1, 1.0 - prob), 2)
            if message.topic in self._config.mask_sender_topics:
                masked = True
        return PerceptionResult(
            perceived=perceived,
            probability=prob,
            distance=distance,
            channel=channel,
            masked=masked,
            suspect_row=suspect_row,
            suspicion_score=suspicion_score,
        )

    def _build_perceived_message(
        self, message: Message, receiver_id: str, result: PerceptionResult
    ) -> Message:
        sender_id = message.sender_id
        content = message.content
        if result.masked:
            sender_id = "unknown"
            parts = []
            if result.suspect_row is not None:
                parts.append(f"suspect_row={result.suspect_row}")
            if result.suspicion_score is not None:
                parts.append(f"suspicion={result.suspicion_score:.2f}")
            parts.append("noise=detected")
            content = ";".join(parts)
        elif result.probability < self._config.degrade_threshold:
            content = self._degrade_content(content)
        if sender_id == message.sender_id and content == message.content:
            return message
        return Message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            topic=message.topic,
            content=content,
            message_id=message.message_id,
            timestamp=message.timestamp,
        )

    def _degrade_content(self, content: str) -> str:
        if ";" in content:
            return f"{content.split(';', 1)[0]};..."
        if len(content) > 24:
            return f"{content[:24]}..."
        return "unclear"

    def _distance_between(self, sender_id: str, receiver_id: str) -> Optional[int]:
        if not self._world or not self._world.layout:
            return None
        sender_loc = self._location_for(sender_id)
        receiver_loc = self._location_for(receiver_id)
        if not sender_loc or not receiver_loc:
            return None
        if sender_loc.scene_id != receiver_loc.scene_id:
            return None
        if not sender_loc.seat_id or not receiver_loc.seat_id:
            return None
        return self._world.layout.distance(sender_loc.seat_id, receiver_loc.seat_id)

    def _profile_for(self, agent_id: str) -> PerceptionProfile:
        role = self._role_for(agent_id)
        if role == AgentRole.TEACHER and self._config.teacher_profile:
            return self._config.teacher_profile
        if role == AgentRole.STUDENT and self._config.student_profile:
            return self._config.student_profile
        return self._config.default_profile

    def _role_for(self, agent_id: str) -> Optional[AgentRole]:
        profile = self._directory.get_profile(agent_id) if self._directory else None
        return profile.role if profile else None

    def _location_for(self, agent_id: str):
        if not self._world:
            return None
        return self._world.location_for(agent_id)

    def _is_occluded(self, profile: PerceptionProfile, sender_id: str) -> bool:
        if not profile.occluded_seats:
            return False
        sender_loc = self._location_for(sender_id)
        if not sender_loc or not sender_loc.seat_id:
            return False
        return sender_loc.seat_id in profile.occluded_seats

    def _log_true(
        self,
        message: Message,
        receiver_id: str,
        prob: float,
        distance: Optional[int],
        channel: str,
    ) -> None:
        self._log_event(
            "TRUE_EVENT",
            message.sender_id,
            receiver_id,
            f"topic={message.topic};prob={prob:.2f};distance={distance};channel={channel}",
        )

    def _log_perceived(
        self,
        message: Message,
        receiver_id: str,
        prob: float,
        distance: Optional[int],
        channel: str,
    ) -> None:
        self._log_event(
            "PERCEIVED_EVENT",
            receiver_id,
            message.sender_id,
            f"topic={message.topic};prob={prob:.2f};distance={distance};channel={channel}",
        )

    def _log_suspicion(
        self,
        receiver_id: str,
        score: float,
        suspect_row: Optional[int],
    ) -> None:
        row_part = f"row={suspect_row}" if suspect_row is not None else "row=unknown"
        self._log_event(
            "SUSPICION_UPDATE",
            receiver_id,
            None,
            f"score={score:.2f};{row_part}",
        )

    def _log_observer_perception(self, message: Message, receiver_id: str) -> None:
        if not self._directory:
            return
        for agent_id in self._directory.all_agents():
            if agent_id in {message.sender_id, receiver_id}:
                continue
            result = self.evaluate(message, agent_id)
            if not result.perceived:
                continue
            self._log_event(
                "PERCEIVED_EVENT",
                agent_id,
                message.sender_id,
                (
                    f"topic={message.topic};prob={result.probability:.2f}"
                    f";distance={result.distance};channel={result.channel}"
                ),
            )

    def _log_event(self, event_type: str, actor_id: str, target_id: Optional[str], content: str) -> None:
        if not self._record_event:
            return
        location = self._location_for(actor_id)
        self._record_event(
            event_type=event_type,
            actor_id=actor_id,
            target_id=target_id,
            scene_id=location.scene_id if location else None,
            seat_id=location.seat_id if location else None,
            object_id=None,
            content=content,
        )
