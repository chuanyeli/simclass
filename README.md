# simclass

Minimal multi-agent campus simulation with identity isolation, persistent memory,
context management, concurrency, and a layered architecture.

## Quick start

```bash
python -m pip install -e .
python -m simclass
```

This runs a 10-student / 3-teacher scenario and stores memory in `data/sim.db`.

## LLM setup (DeepSeek)

Set the API key in your environment (do not hardcode it in files):

```bash
set DEEPSEEK_API_KEY=your_key_here
```

Or create a `.env` file in the repo root with `DEEPSEEK_API_KEY=...`.

LLM can be toggled in `configs/campus_basic.json` under `llm.enabled` or per-agent.
If the key is missing, the simulator falls back to rule-based replies.

## API server

```bash
python -m pip install -e ".[api]"
python -m simclass.api
```

API host/port is read from `configs/campus_basic.json`.

Open the UI at `http://127.0.0.1:8010/`.
Use the Agents panel to edit persona fields or apply templates, then click Reload to apply.
Switch to Classroom View to see the scene layout, seat map, doors, props, and speech bubbles.

Endpoints:

- `GET /status`
- `POST /start`
- `POST /pause`
- `POST /resume`
- `POST /stop`
- `POST /reload`
- `GET /agents`
- `POST /agents`
- `PUT /agents/{agent_id}`
- `DELETE /agents/{agent_id}`
- `GET /persona-templates`
- `POST /agents/{agent_id}/apply-template`
- `GET /messages`
  - Optional query: `direction=outbound|inbound`, `since`, `limit`
- `GET /knowledge`
- `GET /timetable`
- `GET /curriculum-progress`
- `GET /semester`
- `GET /world-state`
- `GET /world-events`
- `WS /ws` (WebSocket stream)

## Simulated calendar & routine

The simulator supports a compressed day clock and weekday/weekend logic:

- `calendar.day_minutes`: minutes per simulated day (e.g. 240 = 24h compressed).
- `calendar.start_time`: when tick 1 starts (e.g. `12:00`).
- `calendar.weekdays`: which days are school days (`Mon`..`Fri`).
- `routine`: wake/breakfast/classes/tests/lunch/school-end timeline.
- `timetable`: class schedule per group/teacher with lesson plans.

Daily tests can be configured with the routine (e.g. 11:20-12:00) and will
measure understanding per topic. Break-time and after-school review events
add small knowledge gains based on persona traits.

## Architecture

- `domain`: core data models (agent profiles, messages).
- `core`: runtime (agents, message bus, context manager, scheduler, simulation).
- `infra`: persistence and logging.
- `app`: scenario loading and wiring.

## Key features

- Identity isolation: each agent has its own context + persistent memory.
- Memory persistence: SQLite-backed store of messages and agent memories.
- Context management: per-agent working memory window with summarization.
- Concurrency: asyncio tasks per agent + queued message passing.
- LLM isolation: per-agent prompt + tool allowlist with restricted execution.
- Layered design: domain/core/infra/app separation.

## Persona fields

Each agent can define a `persona` in `configs/campus_basic.json`:

```json
{
  "persona": {
    "traits": ["curious", "analytical"],
    "tone": "calm",
    "interests": ["math"],
    "bio": "Enjoys problem solving.",
    "engagement": 0.6,
    "confidence": 0.6,
    "collaboration": 0.6
  }
}
```

Templates live under `persona_templates` in `configs/campus_basic.json`.

## Behavior tuning

`configs/campus_basic.json` supports:

```json
{
  "behavior": {
    "student_question_prob": 0.7,
    "office_hours_question_prob": 0.7,
    "student_discuss_prob": 0.5,
    "peer_discuss_prob": 0.6,
    "peer_reply_prob": 0.5
  }
}
```

## Classroom controller

Use `class_session` in `configs/campus_basic.json` to run a teaching cycle:

```
lecture -> question -> group -> summary
```

Configure phase lengths with:

```json
{
  "class_controller": {
    "lecture_ticks": 4,
    "question_ticks": 1,
    "group_ticks": 1,
    "summary_ticks": 1
  }
}
```

## Knowledge state

Each student tracks per-topic understanding. Tests and review events update
the knowledge scores, and teachers adjust strategy based on feedback.

## Perception & world events

Perception can be configured by range/decay/occlusion so messages are not
always observed. The UI can display TRUE/PERCEIVED/SUSPICION world events.

## Project layout

```
configs/
  campus_basic.json
src/simclass/
  app/
  core/
  domain/
  infra/
```
