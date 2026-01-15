from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from simclass.core.llm.responder import LLMResponder
from simclass.domain import AgentRole, Message, SystemEvent


@dataclass(frozen=True)
class OutboundMessage:
    receiver_id: Optional[str]
    topic: str
    content: str


class BaseBehavior:
    async def on_message(self, agent, message: Message) -> List[OutboundMessage]:
        return []

    async def on_event(self, agent, event: SystemEvent) -> List[OutboundMessage]:
        return []


class StudentBehavior(BaseBehavior):
    def __init__(
        self,
        responder: Optional[LLMResponder] = None,
        question_prob: float = 0.7,
        office_hours_prob: float = 0.7,
        discuss_prob: float = 0.5,
        peer_discuss_prob: float = 0.6,
        peer_reply_prob: float = 0.5,
        noise_prob: float = 0.08,
        rng=None,
        social_graph=None,
        world=None,
    ) -> None:
        self._responder = responder
        self._question_prob = question_prob
        self._office_hours_prob = office_hours_prob
        self._discuss_prob = discuss_prob
        self._peer_discuss_prob = peer_discuss_prob
        self._peer_reply_prob = peer_reply_prob
        self._noise_prob = noise_prob
        self._rng = rng
        self._social_graph = social_graph
        self._world = world

    async def on_message(self, agent, message: Message) -> List[OutboundMessage]:
        responses: List[OutboundMessage] = []
        if message.topic == "lecture":
            topic = self._extract_topic(message.content) or "课堂主题"
            understanding = self._understanding_for_topic(agent, topic)
            content = await self._compose(
                agent,
                instruction="请简要确认已收到讲课内容。",
                incoming=f"lecture:{message.content}",
                fallback=f"{agent.profile.name} 已收到关于{message.content}的讲课内容。",
            )
            responses.append(
                OutboundMessage(
                    receiver_id=message.sender_id,
                    topic="ack",
                    content=content,
                )
            )
            if self._roll(self._scale_prob(agent, self._question_prob, "question")):
                level_hint = self._understanding_hint(understanding)
                question = await self._compose(
                    agent,
                    instruction=f"请就讲课内容提出一个简短问题，{level_hint}",
                    incoming=f"lecture:{message.content};理解度={understanding:.2f}",
                    fallback=f"{agent.profile.name} 想就{topic}提一个问题。",
                )
                responses.append(
                    OutboundMessage(
                        receiver_id=message.sender_id,
                        topic="question",
                        content=question,
                    )
                )
            if self._should_noise(agent):
                noise = self._random_noise(agent)
                responses.append(
                    OutboundMessage(
                        receiver_id=message.sender_id,
                        topic="noise",
                        content=noise,
                    )
                )
            responses.extend(self._maybe_object_use(agent, message.sender_id))
        elif message.topic == "quiz":
            topic = self._extract_topic(message.content) or "课堂主题"
            probability = self._scale_prob(agent, 0.85, "question")
            if not self._roll(probability):
                return responses
            understanding = self._understanding_for_topic(agent, topic)
            level_hint = self._understanding_hint(understanding)
            answer = await self._compose(
                agent,
                instruction=(
                    f"你正在参加小测验，请根据理解度作答，{level_hint}。"
                    "请在回答末尾追加 topic=<课程主题>"
                ),
                incoming=f"quiz:{message.content}",
                fallback=(
                    f"{agent.profile.name} 回答了关于{topic}的题目，但仍需完善。"
                    f" topic={topic}"
                ),
            )
            if "topic=" not in answer:
                answer = f"{answer} topic={topic}"
            responses.append(
                OutboundMessage(
                    receiver_id=message.sender_id,
                    topic="quiz_answer",
                    content=answer,
                )
            )
        elif message.topic == "quiz_score":
            topic, score = self._parse_quiz_score(message.content)
            if topic is None or score is None:
                return responses
            updated = self._update_understanding_from_score(agent, topic, score)
            if updated < 0.5:
                feedback = f"topic={topic};level=low;score={updated:.2f}"
                responses.append(
                    OutboundMessage(
                        receiver_id=message.sender_id,
                        topic="feedback",
                        content=feedback,
                    )
                )
            elif updated > 0.85:
                feedback = f"topic={topic};level=high;score={updated:.2f}"
                responses.append(
                    OutboundMessage(
                        receiver_id=message.sender_id,
                        topic="feedback",
                        content=feedback,
                    )
                )
        elif message.topic == "answer":
            content = await self._compose(
                agent,
                instruction="请简短感谢老师的回答。",
                incoming=f"answer:{message.content}",
                fallback=f"{agent.profile.name} 感谢老师的解答。",
            )
            responses.append(
                OutboundMessage(
                    receiver_id=message.sender_id,
                    topic="thanks",
                    content=content,
                )
            )
        elif message.topic == "cold_call":
            content = await self._compose(
                agent,
                instruction="请简短回答老师的点名提问。",
                incoming=f"cold_call:{message.content}",
                fallback=f"{agent.profile.name} 简要复述了要点。",
            )
            responses.append(
                OutboundMessage(
                    receiver_id=message.sender_id,
                    topic="answer",
                    content=content,
                )
            )
        elif message.topic == "announcement":
            return []
        elif message.topic == "office_hours":
            if self._roll(self._scale_prob(agent, self._office_hours_prob, "question")):
                question = await self._compose(
                    agent,
                    instruction="请就项目提出一个简短问题。",
                    incoming=f"office_hours:{message.content}",
                    fallback=f"{agent.profile.name} 想了解项目范围。",
                )
                responses.append(
                    OutboundMessage(
                        receiver_id=message.sender_id,
                        topic="question",
                        content=question,
                    )
                )
        elif message.topic == "peer_comment":
            if self._roll(self._scale_prob(agent, self._peer_reply_prob, "peer")):
                level_hint = self._understanding_hint(
                    self._current_understanding(agent)
                )
                reply = await self._compose(
                    agent,
                    instruction=f"请简短回应同学的观点，{level_hint}",
                    incoming=f"peer:{message.content}",
                    fallback=f"{agent.profile.name} 赞同并补充了看法。",
                )
                responses.append(
                    OutboundMessage(
                        receiver_id=message.sender_id,
                        topic="peer_reply",
                        content=reply,
                    )
                )
        return responses

    async def on_event(self, agent, event: SystemEvent) -> List[OutboundMessage]:
        if event.event_type == "student_discuss":
            probability = float(event.payload.get("probability", self._discuss_prob))
            if not self._roll(self._scale_prob(agent, probability, "question")):
                return []
            topic = event.payload.get("topic", "讨论")
            group = event.payload.get("group", agent.profile.group)
            teachers = agent.directory.group_members(group, role=AgentRole.TEACHER)
            receiver_id = self._pick_one(teachers)
            if receiver_id is None:
                return []
            understanding = self._understanding_for_topic(agent, topic)
            content = await self._compose(
                agent,
                instruction=f"请向老师分享一个简短想法，{self._understanding_hint(understanding)}",
                incoming=f"discussion:{topic}",
                fallback=f"{agent.profile.name} 分享了对{topic}的看法。",
            )
            return [
                OutboundMessage(
                    receiver_id=receiver_id,
                    topic="student_comment",
                    content=content,
                )
            ]
        if event.event_type == "phase_questions":
            probability = float(event.payload.get("probability", self._question_prob))
            if not self._roll(self._scale_prob(agent, probability, "question")):
                return []
            topic = event.payload.get("topic", "讨论")
            teacher_id = event.payload.get("teacher_id")
            if not teacher_id:
                return []
            hint = self._understanding_hint(self._understanding_for_topic(agent, topic))
            question = await self._compose(
                agent,
                instruction=f"请围绕课程主题提出一个简短问题，{hint}",
                incoming=f"question_round:{topic}",
                fallback=f"{agent.profile.name} 想就{topic}提问。",
            )
            return [
                OutboundMessage(
                    receiver_id=teacher_id,
                    topic="question",
                    content=question,
                )
            ]
        if event.event_type == "group_discussion":
            probability = float(event.payload.get("probability", self._peer_discuss_prob))
            if not self._roll(self._scale_prob(agent, probability, "peer")):
                return []
            topic = event.payload.get("topic", "讨论")
            group = event.payload.get("group", agent.profile.group)
            peers = agent.directory.group_members(group, role=AgentRole.STUDENT)
            peers = [peer for peer in peers if peer != agent.profile.agent_id]
            if not peers:
                return []
            receiver_id = self._pick_peer(agent.profile.agent_id, peers)
            understanding = self._understanding_for_topic(agent, topic)
            content = await self._compose(
                agent,
                instruction=f"请和同学交流一个简短观点，{self._understanding_hint(understanding)}",
                incoming=f"group:{topic}",
                fallback=f"{agent.profile.name} 分享了对{topic}的观点。",
            )
            self._record_seat_interaction(agent, receiver_id, "discussion")
            return [
                OutboundMessage(
                    receiver_id=receiver_id,
                    topic="peer_comment",
                    content=content,
                )
            ]
        if event.event_type == "review":
            topics = event.payload.get("topics", [])
            intensity = float(event.payload.get("intensity", 0.04))
            for topic in topics:
                self._review_understanding(agent, topic, intensity)
            return []
        if event.event_type == "routine":
            self._update_state_for_routine(agent, event.payload.get("action", ""))
            return []
        if event.event_type == "day_transition":
            self._apply_forgetting(agent, event.payload.get("day_index"))
            return []
        return []

    async def _compose(self, agent, instruction: str, incoming: str, fallback: str) -> str:
        if not self._responder:
            return fallback
        content = await self._responder.respond(agent, instruction, incoming)
        return content or fallback

    def _scale_prob(self, agent, base_prob: float, mode: str) -> float:
        persona = agent.profile.persona or {}
        state = agent.state
        engagement = float(persona.get("engagement", 0.6))
        confidence = float(persona.get("confidence", 0.6))
        collaboration = float(persona.get("collaboration", 0.6))
        energy = getattr(state, "energy", 0.6)
        attention = getattr(state, "attention", 0.6)
        motivation = getattr(state, "motivation", 0.6)
        stress = getattr(state, "stress", 0.2)
        factor = 0.35 + 0.4 * engagement + 0.15 * motivation
        factor *= 0.6 + 0.4 * energy
        factor *= 0.6 + 0.4 * attention
        factor *= 1.0 - min(0.4, stress)
        if mode == "peer":
            factor *= 0.6 + 0.4 * collaboration
        else:
            factor *= 0.6 + 0.4 * confidence
        scaled = base_prob * factor
        return max(0.05, min(0.95, scaled))

    def _update_understanding_from_score(
        self, agent, topic: str, score: float
    ) -> float:
        current = agent.state.knowledge.get(topic, 0.3)
        blended = current * 0.4 + score * 0.6
        updated = min(0.95, max(0.05, blended))
        agent.state.knowledge[topic] = updated
        self._touch_review(agent, topic)
        if agent.memory_store and hasattr(agent.memory_store, "upsert_knowledge"):
            agent.memory_store.upsert_knowledge(agent.profile.agent_id, topic, updated)
        return updated

    def _review_understanding(self, agent, topic: str, intensity: float) -> float:
        persona = agent.profile.persona or {}
        state = agent.state
        engagement = float(persona.get("engagement", 0.6))
        confidence = float(persona.get("confidence", 0.6))
        energy = getattr(state, "energy", 0.6)
        attention = getattr(state, "attention", 0.6)
        motivation = getattr(state, "motivation", 0.6)
        gain = (
            intensity
            * (0.6 + 0.4 * engagement)
            * (0.7 + 0.3 * confidence)
            * (0.6 + 0.4 * attention)
            * (0.6 + 0.4 * energy)
            * (0.7 + 0.3 * motivation)
        )
        current = agent.state.knowledge.get(topic, 0.3)
        updated = min(0.95, max(0.05, current + gain))
        agent.state.knowledge[topic] = updated
        self._touch_review(agent, topic)
        if agent.memory_store and hasattr(agent.memory_store, "upsert_knowledge"):
            agent.memory_store.upsert_knowledge(agent.profile.agent_id, topic, updated)
        return updated

    def _touch_review(self, agent, topic: str) -> None:
        day_index = getattr(agent.state, "day_index", None)
        if day_index is None:
            return
        last_reviewed = getattr(agent.state, "last_reviewed", None)
        if last_reviewed is None:
            last_reviewed = {}
            agent.state.last_reviewed = last_reviewed
        last_reviewed[topic] = day_index

    def _current_understanding(self, agent) -> float:
        if not agent.state.knowledge:
            return 0.5
        return list(agent.state.knowledge.values())[-1]

    def _understanding_for_topic(self, agent, topic: Optional[str]) -> float:
        if topic and topic in agent.state.knowledge:
            return agent.state.knowledge[topic]
        return self._current_understanding(agent)

    def _extract_topic(self, content: str) -> Optional[str]:
        if "【" in content and "】" in content:
            start = content.find("【") + 1
            end = content.find("】", start)
            if end > start:
                return content[start:end]
        if "topic=" in content:
            parts = content.split("topic=")
            if len(parts) > 1:
                return parts[1].split(";")[0].strip()
        return None

    def _understanding_hint(self, score: float) -> str:
        if score < 0.4:
            return "你对该主题理解较弱"
        if score > 0.8:
            return "你对该主题理解较好"
        return "你对该主题理解一般"

    def _parse_quiz_score(self, content: str) -> tuple[Optional[str], Optional[float]]:
        topic = None
        score = None
        if "topic=" in content:
            topic = content.split("topic=")[1].split(";")[0].strip()
        if "score=" in content:
            score_part = content.split("score=")[1].split(";")[0].strip()
            try:
                score = float(score_part)
            except ValueError:
                score = None
        return topic, score

    def _roll(self, probability: float) -> bool:
        if self._rng:
            return self._rng.random() < probability
        return random.random() < probability

    def _pick_one(self, options: List[str]) -> Optional[str]:
        if not options:
            return None
        if self._rng:
            return self._rng.choice(options)
        return random.choice(options)

    def _pick_peer(self, agent_id: str, peers: List[str]) -> Optional[str]:
        if not peers:
            return None
        if self._world:
            return self._world.pick_peer_with_bias(agent_id, peers, self._rng)
        if self._social_graph:
            return self._social_graph.choose_peer(self._rng, agent_id, peers)
        return self._pick_one(peers)

    def _should_noise(self, agent) -> bool:
        state = agent.state
        attention = getattr(state, "attention", 0.6)
        stress = getattr(state, "stress", 0.2)
        base = self._noise_prob * (1.2 - attention) * (0.8 + 0.4 * stress)
        return self._roll(max(0.02, min(0.3, base)))

    def _random_noise(self, agent) -> str:
        noises = ["走神", "插话", "窃窃私语", "分心翻书"]
        if self._rng:
            noise = self._rng.choice(noises)
        else:
            noise = random.choice(noises)
        return f"{agent.profile.name} {noise}"

    def _maybe_object_use(self, agent, teacher_id: Optional[str]) -> List[OutboundMessage]:
        if not self._world or not self._rng:
            return []
        if self._rng.random() > 0.12:
            return []
        object_id = f"phone.{agent.profile.agent_id}"
        if not self._world.use_object(object_id, agent.profile.agent_id):
            return []
        self._record_object_use(agent, object_id, "use")
        if teacher_id:
            return [
                OutboundMessage(
                    receiver_id=teacher_id,
                    topic="noise",
                    content=f"{agent.profile.name} 偷玩手机",
                )
            ]
        return []

    def _record_seat_interaction(
        self, agent, target_id: Optional[str], action: str
    ) -> None:
        if not self._world or not agent.memory_store:
            return
        location = self._world.location_for(agent.profile.agent_id)
        if not location:
            return
        agent.memory_store.record_world_event(
            event_type="SEAT_INTERACT",
            actor_id=agent.profile.agent_id,
            target_id=target_id,
            scene_id=location.scene_id,
            seat_id=location.seat_id,
            object_id=None,
            content=action,
        )

    def _record_object_use(self, agent, object_id: str, action: str) -> None:
        if not agent.memory_store:
            return
        location = self._world.location_for(agent.profile.agent_id) if self._world else None
        agent.memory_store.record_world_event(
            event_type="OBJECT_USE",
            actor_id=agent.profile.agent_id,
            target_id=None,
            scene_id=location.scene_id if location else None,
            seat_id=location.seat_id if location else None,
            object_id=object_id,
            content=action,
        )

    def _update_state_for_routine(self, agent, action: str) -> None:
        state = agent.state
        if action == "wake":
            state.sleep_debt = max(0.0, state.sleep_debt - 0.2)
            state.energy = min(1.0, state.energy + 0.2)
            state.mood = min(1.0, state.mood + 0.1)
        elif action == "breakfast_start":
            state.energy = min(1.0, state.energy + 0.1)
            state.attention = min(1.0, state.attention + 0.05)
        elif action == "lunch_start":
            state.energy = min(1.0, state.energy + 0.15)
            state.stress = max(0.0, state.stress - 0.1)
        elif action == "school_end":
            state.stress = max(0.0, state.stress - 0.2)
            state.motivation = min(1.0, state.motivation + 0.05)
            state.energy = max(0.2, state.energy - 0.05)

    def _apply_forgetting(self, agent, day_index: Optional[int]) -> None:
        if day_index is None:
            return
        agent.state.day_index = day_index
        last_reviewed = getattr(agent.state, "last_reviewed", {})
        for topic, score in list(agent.state.knowledge.items()):
            last_day = last_reviewed.get(topic, day_index)
            days = max(0, day_index - last_day)
            if days <= 0:
                continue
            decay = 0.97 ** days
            fatigue = 1.0 - min(0.3, agent.state.sleep_debt)
            updated = max(0.05, min(0.95, score * decay * fatigue))
            if updated != score:
                agent.state.knowledge[topic] = updated
                if agent.memory_store and hasattr(agent.memory_store, "upsert_knowledge"):
                    agent.memory_store.upsert_knowledge(
                        agent.profile.agent_id, topic, updated
                    )


class TeacherBehavior(BaseBehavior):
    def __init__(
        self,
        responder: Optional[LLMResponder] = None,
        rng=None,
        curriculum=None,
        world=None,
    ) -> None:
        self._responder = responder
        self._feedback_stats = {}
        self._strategy = {}
        self._quiz_keywords = {}
        self._assessments = {}
        self._rng = rng
        self._curriculum = curriculum
        self._world = world

    async def on_message(self, agent, message: Message) -> List[OutboundMessage]:
        if message.topic == "question":
            content = await self._compose(
                agent,
                instruction="请简短回答学生的问题。",
                incoming=f"question:{message.content}",
                fallback=f"{agent.profile.name} 回答：先抓住基础概念。",
            )
            return [
                OutboundMessage(
                    receiver_id=message.sender_id,
                    topic="answer",
                    content=content,
                )
            ]
        if message.topic == "feedback":
            topic, level, score = self._parse_feedback(message.content)
            if topic:
                stats = self._feedback_stats.setdefault(
                    topic, {"low": 0, "high": 0, "count": 0, "avg_score": 0.6}
                )
                if level == "low":
                    stats["low"] += 1
                elif level == "high":
                    stats["high"] += 1
                if score is not None:
                    count = stats["count"] + 1
                    stats["avg_score"] = (
                        stats["avg_score"] * stats["count"] + score
                    ) / count
                    stats["count"] = count
                self._strategy[topic] = self._decide_strategy(stats)
            return []
        if message.topic == "student_comment":
            content = await self._compose(
                agent,
                instruction="请简短回应学生的观点。",
                incoming=f"comment:{message.content}",
                fallback=f"{agent.profile.name} 觉得这个观点不错。",
            )
            return [
                OutboundMessage(
                    receiver_id=message.sender_id,
                    topic="answer",
                    content=content,
                )
            ]
        if message.topic == "overheard":
            sender_id = message.sender_id
            if sender_id == "unknown" or not sender_id:
                if "from=" in message.content:
                    sender_id = message.content.split("from=", 1)[1].split(";", 1)[0]
                if sender_id == "unknown" or not sender_id:
                    sender_id = None
            if sender_id and self._rng and self._rng.random() < 0.5:
                return [
                    OutboundMessage(
                        receiver_id=sender_id,
                        topic="discipline",
                        content="Please keep the discussion quiet during class.",
                    )
                ]
            if self._rng and self._rng.random() < 0.3:
                recipients = agent.directory.group_members("all", role=AgentRole.STUDENT)
                return [
                    OutboundMessage(
                        receiver_id=student_id,
                        topic="discipline",
                        content="Let's stay focused and lower the noise.",
                    )
                    for student_id in recipients
                ]
            return []

        if message.topic == "noise":
            sender_profile = agent.directory.get_profile(message.sender_id)
            if sender_profile is None or message.sender_id == "unknown":
                suspect_row = self._parse_suspect_row(message.content)
                suspicion = self._parse_suspicion_score(message.content)
                if suspect_row is not None:
                    self._update_suspicion(agent, f"row:{suspect_row}", suspicion or 0.2)
                target_id = self._pick_student_in_row(agent, suspect_row)
                if target_id and self._rng and self._rng.random() < 0.45:
                    return [
                        OutboundMessage(
                            receiver_id=target_id,
                            topic="cold_call",
                            content="Please stay focused and answer the question.",
                        )
                    ]
                if self._rng and self._rng.random() < 0.4:
                    content = await self._compose(
                        agent,
                        instruction="Provide a brief general reminder about classroom discipline.",
                        incoming=f"noise:{message.content}",
                        fallback=f"{agent.profile.name} reminds the class to stay focused.",
                    )
                    recipients = agent.directory.group_members(
                        "all", role=AgentRole.STUDENT
                    )
                    return [
                        OutboundMessage(
                            receiver_id=student_id,
                            topic="discipline",
                            content=content,
                        )
                        for student_id in recipients
                    ]
                return []
            if self._world and not self._world.is_visible(message.sender_id):
                if self._rng and self._rng.random() < 0.6:
                    return []
            content = await self._compose(
                agent,
                instruction="???????????????????????????????????????????????????",
                incoming=f"noise:{message.content}",
                fallback=f"{agent.profile.name} ?????????????????????????????????",
            )
            return [
                OutboundMessage(
                    receiver_id=message.sender_id,
                    topic="discipline",
                    content=content,
                )
            ]
        if message.topic == "quiz_answer":
            topic = self._extract_topic(message.content) or "课堂主题"
            keywords = self._quiz_keywords.get(topic) or self._extract_keywords(
                topic, message.content
            )
            score, feedback = await self._score_answer(
                agent, topic, message.content, keywords
            )
            course_id = self._course_for_concept(topic)
            course_part = f";course={course_id}" if course_id else ""
            payload = f"topic={topic}{course_part};score={score:.2f};feedback={feedback}"
            stats = self._assessments.setdefault(topic, {"scores": [], "avg": 0.6})
            stats["scores"].append(score)
            stats["avg"] = sum(stats["scores"]) / len(stats["scores"])
            return [
                OutboundMessage(
                    receiver_id=message.sender_id,
                    topic="quiz_score",
                    content=payload,
                )
            ]
        return []

    async def on_event(self, agent, event: SystemEvent) -> List[OutboundMessage]:
        if event.event_type in {"lecture", "phase_lecture"}:
            group = event.payload["group"]
            topic = event.payload["topic"]
            recipients = agent.directory.group_members(group, role=AgentRole.STUDENT)
            strategy = self._strategy.get(topic, self._default_strategy())
            lesson_plan = event.payload.get("lesson_plan", "")
            concepts = event.payload.get("concepts", [])
            review_note = self._review_note(concepts)
            instruction = self._lecture_instruction(strategy, lesson_plan, review_note)
            lecture = await self._compose(
                agent,
                instruction=instruction,
                incoming=f"lecture:{topic};plan:{lesson_plan};review:{review_note}",
                fallback=self._fallback_lecture(topic, lesson_plan, event.payload),
            )
            outbound = [
                OutboundMessage(
                    receiver_id=student_id,
                    topic="lecture",
                    content=self._prefix_topic(topic, lecture),
                )
                for student_id in recipients
            ]
            cold_call = self._select_cold_call(recipients)
            if cold_call:
                outbound.append(
                    OutboundMessage(
                        receiver_id=cold_call,
                        topic="cold_call",
                        content=f"{agent.profile.name} 提问：请简要复述刚才的要点。",
                    )
                )
            return outbound
        if event.event_type == "office_hours":
            group = event.payload["group"]
            topic = event.payload["topic"]
            recipients = agent.directory.group_members(group, role=AgentRole.STUDENT)
            note = await self._compose(
                agent,
                instruction="请邀请同学就该主题提问。",
                incoming=f"office_hours:{topic}",
                fallback=f"如果对{topic}有问题，欢迎提问。",
            )
            return [
                OutboundMessage(
                    receiver_id=student_id,
                    topic="office_hours",
                    content=note,
                )
                for student_id in recipients
            ]
        if event.event_type == "phase_summary":
            group = event.payload["group"]
            topic = event.payload["topic"]
            recipients = agent.directory.group_members(group, role=AgentRole.STUDENT)
            strategy = self._strategy.get(topic, self._default_strategy())
            lesson_plan = event.payload.get("lesson_plan", "")
            instruction = self._summary_instruction(strategy)
            summary = await self._compose(
                agent,
                instruction=instruction,
                incoming=f"summary:{topic};plan:{lesson_plan}",
                fallback=self._fallback_summary(topic, lesson_plan, event.payload),
            )
            outbound = [
                OutboundMessage(
                    receiver_id=student_id,
                    topic="summary",
                    content=self._prefix_topic(topic, summary),
                )
                for student_id in recipients
            ]
            concepts = event.payload.get("concepts", [])
            quiz_targets = self._select_quiz_concepts(concepts, limit=2)
            for concept_id in quiz_targets:
                concept_name = self._concept_name(concept_id)
                quiz_question = await self._build_quiz_question(
                    agent, concept_id, concept_name, lesson_plan
                )
                self._quiz_keywords[concept_id] = self._extract_keywords(
                    concept_id, quiz_question
                )
                for student_id in recipients:
                    outbound.append(
                        OutboundMessage(
                            receiver_id=student_id,
                            topic="quiz",
                            content=quiz_question,
                        )
                    )
            return outbound
        if event.event_type == "daily_test":
            group = event.payload["group"]
            concepts = event.payload.get("concepts", [])
            recipients = agent.directory.group_members(group, role=AgentRole.STUDENT)
            if not recipients or not concepts:
                return []
            outbound: List[OutboundMessage] = []
            for concept_id in concepts:
                concept_name = self._concept_name(concept_id)
                quiz_question = await self._build_quiz_question(
                    agent, concept_id, concept_name, "昨日课程测验"
                )
                self._quiz_keywords[concept_id] = self._extract_keywords(
                    concept_id, quiz_question
                )
                for student_id in recipients:
                    outbound.append(
                        OutboundMessage(
                            receiver_id=student_id,
                            topic="quiz",
                            content=quiz_question,
                        )
                    )
            return outbound
        return []

    async def _compose(self, agent, instruction: str, incoming: str, fallback: str) -> str:
        if not self._responder:
            return fallback
        content = await self._responder.respond(agent, instruction, incoming)
        return content or fallback

    def _parse_feedback(
        self, content: str
    ) -> tuple[Optional[str], Optional[str], Optional[float]]:
        if "topic=" not in content or "level=" not in content:
            return None, None, None
        topic_part = content.split("topic=")[1]
        topic = topic_part.split(";")[0].strip()
        level_part = content.split("level=")[1]
        level = level_part.split(";")[0].strip()
        score = None
        if "score=" in content:
            score_part = content.split("score=")[1]
            score_text = score_part.split(";")[0].strip()
            try:
                score = float(score_text)
            except ValueError:
                score = None
        return topic, level, score

    def _default_strategy(self) -> dict:
        return {"mode": "normal", "style": "平衡讲解", "pace": "中等", "examples": 2}

    def _decide_strategy(self, stats: dict) -> dict:
        low = int(stats.get("low", 0))
        high = int(stats.get("high", 0))
        avg = float(stats.get("avg_score", 0.6))
        mode = "normal"
        if low >= high + 1 or avg < 0.45:
            mode = "basic"
        elif high >= low + 1 and avg > 0.75:
            mode = "advanced"
        if mode == "basic":
            style = "基础讲解"
        elif mode == "advanced":
            style = "进阶讲解"
        else:
            style = "平衡讲解"
        if avg < 0.5:
            pace = "慢"
        elif avg > 0.8:
            pace = "快"
        else:
            pace = "中等"
        if avg < 0.5:
            examples = 3
        elif avg > 0.8:
            examples = 1
        else:
            examples = 2
        return {"mode": mode, "style": style, "pace": pace, "examples": examples}

    def _lecture_instruction(
        self, strategy: dict, lesson_plan: str, review_note: str
    ) -> str:
        style = strategy.get("style", "平衡讲解")
        pace = strategy.get("pace", "中等")
        examples = strategy.get("examples", 2)
        extra = ""
        if lesson_plan:
            extra = f"本节讲解要点：{lesson_plan}。"
        if review_note:
            extra = f"{extra} 需要回顾：{review_note}。"
        return (
            f"请采用{style}方式讲解，节奏{pace}，给出{examples}个例子，"
            f"突出关键概念和易错点。{extra}"
        )

    def _summary_instruction(self, strategy: dict) -> str:
        style = strategy.get("style", "平衡讲解")
        pace = strategy.get("pace", "中等")
        examples = strategy.get("examples", 2)
        return (
            f"请做简短总结，延续{style}风格，节奏{pace}，"
            f"补充{examples}个关键例子或应用场景。"
        )

    def _prefix_topic(self, topic: str, content: str) -> str:
        if content.startswith("【"):
            return content
        return f"【{topic}】{content}"

    def _extract_topic(self, content: str) -> Optional[str]:
        if "【" in content and "】" in content:
            start = content.find("【") + 1
            end = content.find("】", start)
            if end > start:
                return content[start:end]
        if "topic=" in content:
            parts = content.split("topic=")
            if len(parts) > 1:
                return parts[1].split(";")[0].strip()
        return None

    def _extract_keywords(self, topic: str, question: str) -> list[str]:
        keywords = []
        if topic:
            keywords.append(topic)
        for token in ("定义", "概念", "步骤", "应用", "原理"):
            if token in question:
                keywords.append(token)
        if not keywords:
            keywords = ["要点"]
        return list(dict.fromkeys(keywords))

    async def _score_answer(
        self, agent, topic: str, answer: str, keywords: list[str]
    ) -> tuple[float, str]:
        if self._responder:
            instruction = (
                "你是老师，请根据关键词为学生回答打分。"
                "输出格式：score=<0到1之间的小数>;feedback=<简短评语>"
            )
            incoming = (
                f"topic:{topic};keywords:{','.join(keywords)};answer:{answer}"
            )
            response = await self._compose(
                agent,
                instruction=instruction,
                incoming=incoming,
                fallback="score=0.6;feedback=回答有一定理解，但不够完整。",
            )
            parsed = self._parse_score_response(response)
            if parsed:
                return parsed
        return self._heuristic_score(answer, keywords)

    def _parse_score_response(self, content: str) -> Optional[tuple[float, str]]:
        if "score=" not in content:
            return None
        try:
            score_part = content.split("score=")[1].split(";")[0].strip()
            score = float(score_part)
        except ValueError:
            return None
        feedback = ""
        if "feedback=" in content:
            feedback = content.split("feedback=")[1].strip()
        score = min(1.0, max(0.0, score))
        if not feedback:
            feedback = "回答已覆盖部分要点。"
        return score, feedback

    def _review_note(self, concepts: list[str]) -> str:
        if not concepts:
            return ""
        weak = []
        for concept_id in concepts:
            stats = self._assessments.get(concept_id)
            if stats and stats.get("scores") and stats["avg"] < 0.6:
                weak.append(concept_id)
        if weak:
            return f"需回顾薄弱知识点: {', '.join(weak[:2])}"
        return ""

    def _fallback_lecture(self, topic: str, lesson_plan: str, payload: dict) -> str:
        concepts = payload.get("concepts", [])
        concept_text = "、".join(concepts) if concepts else "暂无知识点"
        if lesson_plan:
            return f"【{topic}】{lesson_plan}。知识点: {concept_text}"
        return f"【{topic}】本节课知识点: {concept_text}"

    def _fallback_summary(self, topic: str, lesson_plan: str, payload: dict) -> str:
        concepts = payload.get("concepts", [])
        concept_text = "、".join(concepts) if concepts else "暂无知识点"
        if lesson_plan:
            return f"【{topic}】回顾: {lesson_plan}。知识点: {concept_text}"
        return f"【{topic}】总结知识点: {concept_text}"

    def _concept_name(self, concept_id: str) -> str:
        if self._curriculum:
            concept = self._curriculum._concepts.get(concept_id)
            if concept:
                return concept.name
        return concept_id

    def _course_for_concept(self, concept_id: str) -> Optional[str]:
        if self._curriculum:
            return self._curriculum.course_for_concept(concept_id)
        return None

    def _select_quiz_concepts(self, concepts: list[str], limit: int) -> list[str]:
        if not concepts:
            return []
        sorted_concepts = sorted(
            concepts,
            key=lambda cid: self._assessments.get(cid, {}).get("avg", 0.6),
        )
        return sorted_concepts[: max(1, min(limit, len(sorted_concepts)))]

    def _select_cold_call(self, recipients: list[str]) -> Optional[str]:
        if not recipients:
            return None
        if not self._rng or self._rng.random() > 0.25:
            return None
        return self._rng.choice(recipients)

    def _parse_suspect_row(self, content: str) -> Optional[int]:
        if not content:
            return None
        for key in ("suspect_row", "row"):
            token = f"{key}="
            if token not in content:
                continue
            try:
                value = content.split(token, 1)[1].split(";", 1)[0]
                return int(value)
            except ValueError:
                return None
        return None

    def _parse_suspicion_score(self, content: str) -> Optional[float]:
        if "suspicion=" not in content:
            return None
        try:
            value = content.split("suspicion=", 1)[1].split(";", 1)[0]
            return float(value)
        except ValueError:
            return None

    def _update_suspicion(self, agent, key: str, delta: float) -> None:
        if not hasattr(agent, "state"):
            return
        current = agent.state.suspicion.get(key, 0.0)
        agent.state.suspicion[key] = min(1.0, current + max(0.0, delta))

    def _pick_student_in_row(self, agent, row: Optional[int]) -> Optional[str]:
        if row is None or not self._world:
            return None
        candidates = []
        for student_id in agent.directory.group_members("all", role=AgentRole.STUDENT):
            location = self._world.location_for(student_id)
            if location and location.row == row:
                candidates.append(student_id)
        if not candidates:
            return None
        if self._rng:
            return self._rng.choice(candidates)
        return candidates[0]

    async def _build_quiz_question(
        self, agent, concept_id: str, concept_name: str, context: str
    ) -> str:
        instruction = "请出一道针对知识点的小测验题，问题简短，不要给出答案。"
        course_id = self._course_for_concept(concept_id) or ""
        incoming = f"concept:{concept_id};name:{concept_name};course:{course_id};context:{context}"
        fallback = ""
        if self._curriculum:
            template = self._curriculum.question_bank.question_for(concept_id, self._rng)
            if template:
                fallback = template
        if not fallback:
            fallback = f"请简要说明知识点 {concept_name} 的核心概念。"
        question = await self._compose(
            agent,
            instruction=instruction,
            incoming=incoming,
            fallback=fallback,
        )
        return self._prefix_topic(concept_id, question)

    def _heuristic_score(
        self, answer: str, keywords: list[str]
    ) -> tuple[float, str]:
        clean = answer.lower()
        hits = 0
        usable = [kw for kw in keywords if kw]
        for keyword in usable:
            if keyword.lower() in clean:
                hits += 1
        ratio = hits / max(1, len(usable))
        length_score = min(1.0, max(0.0, (len(answer) - 10) / 60))
        score = 0.2 + 0.6 * ratio + 0.2 * length_score
        score = min(0.95, max(0.05, score))
        if ratio < 0.4:
            feedback = "回答未覆盖关键点，建议补充核心概念。"
        elif ratio < 0.8:
            feedback = "回答覆盖部分要点，可再补充细节。"
        else:
            feedback = "回答较完整，关键点覆盖充分。"
        return score, feedback
