from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from simclass.domain import Message


@dataclass(frozen=True)
class MemoryRecord:
    agent_id: str
    kind: str
    content: str
    timestamp: float


@dataclass(frozen=True)
class MessageEvent:
    message_id: str
    sender_id: str
    receiver_id: Optional[str]
    topic: str
    content: str
    timestamp: float
    agent_id: str
    direction: str


@dataclass(frozen=True)
class KnowledgeRecord:
    agent_id: str
    topic: str
    score: float
    updated_at: float


class SQLiteMemoryStore:
    def __init__(self, db_path: Path, *, on_message_event=None) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._on_message_event = on_message_event
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    sender_id TEXT NOT NULL,
                    receiver_id TEXT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS message_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    receiver_id TEXT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    agent_id TEXT NOT NULL,
                    direction TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    receiver_id TEXT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    reason TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    score REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(agent_id, topic)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sim_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.commit()

    def record_message(self, message: Message) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO messages (
                    message_id, sender_id, receiver_id, topic, content, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.sender_id,
                    message.receiver_id,
                    message.topic,
                    message.content,
                    message.timestamp,
                ),
            )
            self._conn.commit()

    def record_message_event(self, message: Message, agent_id: str, direction: str) -> None:
        event = MessageEvent(
            message_id=message.message_id,
            sender_id=message.sender_id,
            receiver_id=message.receiver_id,
            topic=message.topic,
            content=message.content,
            timestamp=message.timestamp,
            agent_id=agent_id,
            direction=direction,
        )
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO message_events (
                    message_id, sender_id, receiver_id, topic, content, timestamp, agent_id, direction
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.message_id,
                    event.sender_id,
                    event.receiver_id,
                    event.topic,
                    event.content,
                    event.timestamp,
                    event.agent_id,
                    event.direction,
                ),
            )
            self._conn.commit()
        if self._on_message_event:
            self._on_message_event(event)

    def record_memory(self, agent_id: str, kind: str, content: str, timestamp: float) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_memory (agent_id, kind, content, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (agent_id, kind, content, timestamp),
            )
            self._conn.commit()

    def record_dead_letter(self, message: Message, reason: str) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO dead_letters (
                    message_id, sender_id, receiver_id, topic, content, timestamp, reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.sender_id,
                    message.receiver_id,
                    message.topic,
                    message.content,
                    message.timestamp,
                    reason,
                ),
            )
            self._conn.commit()

    def upsert_knowledge(self, agent_id: str, topic: str, score: float) -> None:
        timestamp = time.time()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_knowledge (agent_id, topic, score, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(agent_id, topic)
                DO UPDATE SET score = excluded.score, updated_at = excluded.updated_at
                """,
                (agent_id, topic, float(score), timestamp),
            )
            self._conn.commit()

    def load_knowledge(self, agent_id: str) -> dict:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT topic, score
                FROM agent_knowledge
                WHERE agent_id = ?
                ORDER BY updated_at ASC
                """,
                (agent_id,),
            )
            rows = cursor.fetchall()
        return {row[0]: float(row[1]) for row in rows}

    def list_knowledge(self, agent_id: Optional[str] = None) -> List[KnowledgeRecord]:
        with self._lock:
            cursor = self._conn.cursor()
            if agent_id:
                cursor.execute(
                    """
                    SELECT agent_id, topic, score, updated_at
                    FROM agent_knowledge
                    WHERE agent_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (agent_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT agent_id, topic, score, updated_at
                    FROM agent_knowledge
                    ORDER BY updated_at DESC
                    """,
                )
            rows = cursor.fetchall()
        return [
            KnowledgeRecord(
                agent_id=row[0], topic=row[1], score=float(row[2]), updated_at=row[3]
            )
            for row in rows
        ]

    def load_recent_memory(self, agent_id: str, limit: int = 20) -> List[MemoryRecord]:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT agent_id, kind, content, timestamp
                FROM agent_memory
                WHERE agent_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (agent_id, limit),
            )
            rows = cursor.fetchall()
        return [
            MemoryRecord(
                agent_id=row[0], kind=row[1], content=row[2], timestamp=row[3]
            )
            for row in rows
        ]

    def list_message_events(
        self,
        limit: int = 50,
        since_ts: Optional[float] = None,
        direction: Optional[str] = None,
    ) -> List[MessageEvent]:
        with self._lock:
            cursor = self._conn.cursor()
            if since_ts is None:
                if direction:
                    cursor.execute(
                        """
                        SELECT message_id, sender_id, receiver_id, topic, content, timestamp, agent_id, direction
                        FROM message_events
                        WHERE direction = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (direction, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT message_id, sender_id, receiver_id, topic, content, timestamp, agent_id, direction
                        FROM message_events
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
            else:
                if direction:
                    cursor.execute(
                        """
                        SELECT message_id, sender_id, receiver_id, topic, content, timestamp, agent_id, direction
                        FROM message_events
                        WHERE timestamp > ? AND direction = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (since_ts, direction, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT message_id, sender_id, receiver_id, topic, content, timestamp, agent_id, direction
                        FROM message_events
                        WHERE timestamp > ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (since_ts, limit),
                    )
            rows = cursor.fetchall()
        return [
            MessageEvent(
                message_id=row[0],
                sender_id=row[1],
                receiver_id=row[2],
                topic=row[3],
                content=row[4],
                timestamp=row[5],
                agent_id=row[6],
                direction=row[7],
            )
            for row in rows
        ]

    def get_last_tick(self) -> int:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT value
                FROM sim_state
                WHERE key = 'last_tick'
                """,
            )
            row = cursor.fetchone()
        if not row:
            return 1
        try:
            return max(1, int(row[0]))
        except (TypeError, ValueError):
            return 1

    def set_last_tick(self, tick: int) -> None:
        timestamp = time.time()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO sim_state (key, value, updated_at)
                VALUES ('last_tick', ?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (str(int(tick)), timestamp),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
