from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from simclass.app.config import resolve_paths
from simclass.app.llm_factory import LLMFactory
from simclass.app.scenario import load_scenario
from simclass.core.simulation import Simulation
from simclass.core.tools import build_default_tools
from simclass.infra import SQLiteMemoryStore, configure_logging, load_dotenv


@dataclass
class ApiResponse:
    status: str
    detail: str = ""


class WebSocketHub:
    def __init__(self) -> None:
        self._connections = set()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        asyncio.create_task(self._run())

    def publish(self, event) -> None:
        if not self._loop:
            return
        payload = {
            "message_id": event.message_id,
            "sender_id": event.sender_id,
            "receiver_id": event.receiver_id,
            "topic": event.topic,
            "content": event.content,
            "timestamp": event.timestamp,
            "agent_id": event.agent_id,
            "direction": event.direction,
        }
        self._loop.call_soon_threadsafe(self._queue.put_nowait, payload)

    async def connect(self, websocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._connections.discard(websocket)

    async def _run(self) -> None:
        while True:
            payload = await self._queue.get()
            if not self._connections:
                continue
            stale = []
            for websocket in list(self._connections):
                try:
                    await websocket.send_json(payload)
                except Exception:  # noqa: BLE001
                    stale.append(websocket)
            for websocket in stale:
                self._connections.discard(websocket)


class SimulationService:
    def __init__(self, hub) -> None:
        self._paths = resolve_paths()
        self._task: Optional[asyncio.Task] = None
        self._simulation: Optional[Simulation] = None
        self._lock = asyncio.Lock()
        self._hub = hub
        self._logger = logging.getLogger("api.service")

    async def start(self) -> ApiResponse:
        async with self._lock:
            if self._task and not self._task.done():
                return ApiResponse(status="running", detail="simulation already running")
            scenario = load_scenario(self._paths.config_path)
            store = SQLiteMemoryStore(
                self._paths.data_path, on_message_event=self._hub.publish
            )
            llm_factory = LLMFactory(scenario.llm)
            tool_registry = build_default_tools()
            self._simulation = Simulation(
                scenario, store, llm_factory, tool_registry
            )
            self._task = asyncio.create_task(self._simulation.run())
            return ApiResponse(status="started")

    async def stop(self) -> ApiResponse:
        async with self._lock:
            if not self._simulation:
                return ApiResponse(status="stopped", detail="no simulation")
            self._simulation.stop()
            if self._task:
                await self._task
            self._simulation = None
            self._task = None
            return ApiResponse(status="stopped")

    async def pause(self) -> ApiResponse:
        async with self._lock:
            if not self._simulation:
                return ApiResponse(status="error", detail="no simulation")
            self._simulation.pause()
            return ApiResponse(status="paused")

    async def resume(self) -> ApiResponse:
        async with self._lock:
            if not self._simulation:
                return ApiResponse(status="error", detail="no simulation")
            self._simulation.resume()
            return ApiResponse(status="running")

    async def reload(self) -> ApiResponse:
        await self.stop()
        return await self.start()

    async def status(self) -> dict:
        if not self._simulation:
            return {"running": False, "paused": False, "current_tick": 0}
        return self._simulation.status()

    def load_config(self) -> dict:
        return json.loads(self._paths.config_path.read_text(encoding="utf-8-sig"))

    def save_config(self, data: dict) -> None:
        tmp_path = self._paths.config_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(self._paths.config_path)

    def list_templates(self) -> dict:
        config = self.load_config()
        return config.get("persona_templates", {})

    def list_timetable(self) -> list[dict]:
        config = self.load_config()
        return config.get("timetable", [])

    def list_messages(
        self,
        limit: int = 50,
        since_ts: Optional[float] = None,
        direction: Optional[str] = None,
    ) -> list[dict]:
        store = SQLiteMemoryStore(self._paths.data_path)
        try:
            events = store.list_message_events(
                limit=limit, since_ts=since_ts, direction=direction
            )
            return [
                {
                    "message_id": event.message_id,
                    "sender_id": event.sender_id,
                    "receiver_id": event.receiver_id,
                    "topic": event.topic,
                    "content": event.content,
                    "timestamp": event.timestamp,
                    "agent_id": event.agent_id,
                    "direction": event.direction,
                }
                for event in events
            ]
        finally:
            store.close()

    def list_knowledge(self, agent_id: Optional[str] = None) -> list[dict]:
        store = SQLiteMemoryStore(self._paths.data_path)
        try:
            records = store.list_knowledge(agent_id=agent_id)
            return [
                {
                    "agent_id": record.agent_id,
                    "topic": record.topic,
                    "score": record.score,
                    "updated_at": record.updated_at,
                }
                for record in records
            ]
        finally:
            store.close()


def create_app():
    try:
        from fastapi import FastAPI, HTTPException, Query, WebSocket
        from fastapi.responses import FileResponse, HTMLResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "FastAPI is not installed. Install with: pip install -e \".[api]\""
        ) from exc

    paths = resolve_paths()
    load_dotenv(paths.root / ".env")
    hub = WebSocketHub()
    service = SimulationService(hub)
    app = FastAPI()
    ui_dir = Path(__file__).resolve().parent / "web"
    if ui_dir.exists():
        app.mount("/ui", StaticFiles(directory=ui_dir), name="ui")

    @app.on_event("startup")
    async def startup():
        hub.bind_loop(asyncio.get_running_loop())

    @app.get("/status")
    async def get_status():
        return await service.status()

    @app.post("/start")
    async def start():
        return (await service.start()).__dict__

    @app.post("/stop")
    async def stop():
        return (await service.stop()).__dict__

    @app.post("/pause")
    async def pause():
        return (await service.pause()).__dict__

    @app.post("/resume")
    async def resume():
        return (await service.resume()).__dict__

    @app.post("/reload")
    async def reload():
        return (await service.reload()).__dict__

    @app.get("/")
    async def root():
        index_path = ui_dir / "index.html"
        if not index_path.exists():
            return HTMLResponse("<h3>UI not found</h3>", status_code=404)
        return FileResponse(index_path)

    @app.get("/config")
    async def get_config():
        return service.load_config()

    @app.put("/config")
    async def put_config(payload: dict):
        service.save_config(payload)
        return {"status": "ok"}

    @app.get("/agents")
    async def get_agents():
        config = service.load_config()
        return config.get("agents", [])

    @app.post("/agents")
    async def add_agent(payload: dict):
        config = service.load_config()
        agents = config.get("agents", [])
        agent_id = payload.get("id")
        if not agent_id:
            raise HTTPException(status_code=400, detail="id is required")
        if not payload.get("name") or not payload.get("group") or not payload.get("role"):
            raise HTTPException(status_code=400, detail="name, role, group are required")
        if any(agent.get("id") == agent_id for agent in agents):
            raise HTTPException(status_code=400, detail="id already exists")
        payload.setdefault("llm", {"enabled": True})
        payload.setdefault("persona", {})
        agents.append(payload)
        config["agents"] = agents
        service.save_config(config)
        return {"status": "ok"}

    @app.put("/agents/{agent_id}")
    async def update_agent(agent_id: str, payload: dict):
        config = service.load_config()
        agents = config.get("agents", [])
        found = False
        for agent in agents:
            if agent.get("id") == agent_id:
                agent.update(payload)
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="agent not found")
        config["agents"] = agents
        service.save_config(config)
        return {"status": "ok"}

    @app.delete("/agents/{agent_id}")
    async def delete_agent(agent_id: str):
        config = service.load_config()
        agents = config.get("agents", [])
        updated = [agent for agent in agents if agent.get("id") != agent_id]
        if len(updated) == len(agents):
            raise HTTPException(status_code=404, detail="agent not found")
        config["agents"] = updated
        service.save_config(config)
        return {"status": "ok"}

    @app.get("/persona-templates")
    async def get_persona_templates():
        return service.list_templates()

    @app.get("/timetable")
    async def get_timetable():
        return service.list_timetable()

    @app.post("/agents/{agent_id}/apply-template")
    async def apply_template(agent_id: str, payload: dict):
        template_name = payload.get("template")
        if not template_name:
            raise HTTPException(status_code=400, detail="template is required")
        templates = service.list_templates()
        if template_name not in templates:
            raise HTTPException(status_code=404, detail="template not found")
        config = service.load_config()
        agents = config.get("agents", [])
        found = False
        for agent in agents:
            if agent.get("id") == agent_id:
                agent["persona"] = templates[template_name]
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="agent not found")
        config["agents"] = agents
        service.save_config(config)
        return {"status": "ok"}

    @app.get("/messages")
    async def get_messages(
        limit: int = Query(50, ge=1, le=200),
        since: Optional[float] = None,
        direction: Optional[str] = Query(None, pattern="^(inbound|outbound)$"),
    ):
        return service.list_messages(limit=limit, since_ts=since, direction=direction)

    @app.get("/knowledge")
    async def get_knowledge(agent_id: Optional[str] = None):
        return service.list_knowledge(agent_id=agent_id)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await hub.connect(websocket)

    return app


def run() -> None:
    try:
        import uvicorn
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "uvicorn is not installed. Install with: pip install -e \".[api]\""
        ) from exc

    configure_logging()
    paths = resolve_paths()
    load_dotenv(paths.root / ".env")
    scenario = load_scenario(paths.config_path)
    app = create_app()
    uvicorn.run(app, host=scenario.api.host, port=scenario.api.port)
