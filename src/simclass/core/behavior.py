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
    ) -> None:
        self._responder = responder
        self._question_prob = question_prob
        self._office_hours_prob = office_hours_prob
        self._discuss_prob = discuss_prob
        self._peer_discuss_prob = peer_discuss_prob
        self._peer_reply_prob = peer_reply_prob

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
            if random.random() < self._scale_prob(agent, self._question_prob, "question"):
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
        elif message.topic == "quiz":
            topic = self._extract_topic(message.content) or "课堂主题"
            probability = self._scale_prob(agent, 0.85, "question")
            if random.random() > probability:
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
        elif message.topic == "announcement":
            return []
        elif message.topic == "office_hours":
            if random.random() < self._scale_prob(agent, self._office_hours_prob, "question"):
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
            if random.random() < self._scale_prob(agent, self._peer_reply_prob, "peer"):
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
            if random.random() > self._scale_prob(agent, probability, "question"):
                return []
            topic = event.payload.get("topic", "讨论")
            group = event.payload.get("group", agent.profile.group)
            teachers = agent.directory.group_members(group, role=AgentRole.TEACHER)
            receiver_id = random.choice(teachers) if teachers else None
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
            if random.random() > self._scale_prob(agent, probability, "question"):
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
            if random.random() > self._scale_prob(agent, probability, "peer"):
                return []
            topic = event.payload.get("topic", "讨论")
            group = event.payload.get("group", agent.profile.group)
            peers = agent.directory.group_members(group, role=AgentRole.STUDENT)
            peers = [peer for peer in peers if peer != agent.profile.agent_id]
            if not peers:
                return []
            receiver_id = random.choice(peers)
            understanding = self._understanding_for_topic(agent, topic)
            content = await self._compose(
                agent,
                instruction=f"请和同学交流一个简短观点，{self._understanding_hint(understanding)}",
                incoming=f"group:{topic}",
                fallback=f"{agent.profile.name} 分享了对{topic}的观点。",
            )
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
        return []

    async def _compose(self, agent, instruction: str, incoming: str, fallback: str) -> str:
        if not self._responder:
            return fallback
        content = await self._responder.respond(agent, instruction, incoming)
        return content or fallback

    def _scale_prob(self, agent, base_prob: float, mode: str) -> float:
        persona = agent.profile.persona or {}
        engagement = float(persona.get("engagement", 0.6))
        confidence = float(persona.get("confidence", 0.6))
        collaboration = float(persona.get("collaboration", 0.6))
        factor = 0.4 + 0.6 * engagement
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
        if agent.memory_store and hasattr(agent.memory_store, "upsert_knowledge"):
            agent.memory_store.upsert_knowledge(agent.profile.agent_id, topic, updated)
        return updated

    def _review_understanding(self, agent, topic: str, intensity: float) -> float:
        persona = agent.profile.persona or {}
        engagement = float(persona.get("engagement", 0.6))
        confidence = float(persona.get("confidence", 0.6))
        gain = intensity * (0.6 + 0.4 * engagement) * (0.7 + 0.3 * confidence)
        current = agent.state.knowledge.get(topic, 0.3)
        updated = min(0.95, max(0.05, current + gain))
        agent.state.knowledge[topic] = updated
        if agent.memory_store and hasattr(agent.memory_store, "upsert_knowledge"):
            agent.memory_store.upsert_knowledge(agent.profile.agent_id, topic, updated)
        return updated

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


class TeacherBehavior(BaseBehavior):
    def __init__(self, responder: Optional[LLMResponder] = None) -> None:
        self._responder = responder
        self._feedback_stats = {}
        self._strategy = {}
        self._quiz_keywords = {}
        self._assessments = {}

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
        if message.topic == "quiz_answer":
            topic = self._extract_topic(message.content) or "课堂主题"
            keywords = self._quiz_keywords.get(topic) or self._extract_keywords(
                topic, message.content
            )
            score, feedback = await self._score_answer(
                agent, topic, message.content, keywords
            )
            payload = f"topic={topic};score={score:.2f};feedback={feedback}"
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
            review_note = self._review_note(topic)
            instruction = self._lecture_instruction(strategy, lesson_plan, review_note)
            lecture = await self._compose(
                agent,
                instruction=instruction,
                incoming=f"lecture:{topic};plan:{lesson_plan};review:{review_note}",
                fallback=f"【{topic}】今天我们学习{topic}的基础概念。",
            )
            return [
                OutboundMessage(
                    receiver_id=student_id,
                    topic="lecture",
                    content=self._prefix_topic(topic, lecture),
                )
                for student_id in recipients
            ]
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
                fallback=f"【{topic}】今天的重点是掌握基础概念并能应用。",
            )
            outbound = [
                OutboundMessage(
                    receiver_id=student_id,
                    topic="summary",
                    content=self._prefix_topic(topic, summary),
                )
                for student_id in recipients
            ]
            quiz_question = await self._compose(
                agent,
                instruction="请出一道与主题相关的小测验题，问题简短，不要给出答案。",
                incoming=f"quiz:{topic};plan:{lesson_plan}",
                fallback=f"请简要说明{topic}的核心概念。",
            )
            quiz_question = self._prefix_topic(topic, quiz_question)
            self._quiz_keywords[topic] = self._extract_keywords(topic, quiz_question)
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
            topics = event.payload.get("topics", [])
            recipients = agent.directory.group_members(group, role=AgentRole.STUDENT)
            if not recipients or not topics:
                return []
            outbound: List[OutboundMessage] = []
            for topic in topics:
                quiz_question = await self._compose(
                    agent,
                    instruction="请出一道与主题相关的小测验题，问题简短，不要给出答案。",
                    incoming=f"quiz:{topic};purpose:daily_test",
                    fallback=f"请简要说明{topic}的核心概念。",
                )
                quiz_question = self._prefix_topic(topic, quiz_question)
                self._quiz_keywords[topic] = self._extract_keywords(topic, quiz_question)
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

    def _review_note(self, topic: str) -> str:
        stats = self._assessments.get(topic)
        if not stats or not stats.get("scores"):
            return ""
        if stats["avg"] < 0.6:
            return "上一轮测验平均分偏低，需要简要回顾上次内容"
        return ""

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
