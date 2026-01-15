from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class AgentLocation:
    scene_id: str
    seat_id: Optional[str] = None
    row: Optional[int] = None
    col: Optional[int] = None


@dataclass(frozen=True)
class Scene:
    scene_id: str
    scene_type: str
    layout_id: Optional[str] = None


@dataclass
class WorldObject:
    object_id: str
    object_type: str
    scene_id: Optional[str] = None
    state: str = "available"
    holder_id: Optional[str] = None
    owner_id: Optional[str] = None


class ClassroomLayout:
    def __init__(
        self,
        rows: int,
        cols: int,
        seat_map: Optional[List[List[Optional[str]]]] = None,
        empty_seats: Optional[Iterable[str]] = None,
        teacher_desk: Optional[dict] = None,
        doors: Optional[List[dict]] = None,
    ) -> None:
        self.rows = max(1, int(rows))
        self.cols = max(1, int(cols))
        self._seat_map = seat_map
        self._empty_seats = set(empty_seats or [])
        self.teacher_desk = teacher_desk or {"row": 0, "col": max(0, self.cols // 2)}
        self.doors = doors or []
        self._seat_positions: Dict[str, Tuple[int, int]] = {}
        self._build_seats()

    @classmethod
    def from_config(cls, cfg: dict) -> "ClassroomLayout":
        return cls(
            rows=int(cfg.get("rows", 4)),
            cols=int(cfg.get("cols", 5)),
            seat_map=cfg.get("seat_map"),
            empty_seats=cfg.get("empty_seats", []),
            teacher_desk=cfg.get("teacher_desk"),
            doors=cfg.get("doors", []),
        )

    def _build_seats(self) -> None:
        if self._seat_map:
            for row_index, row in enumerate(self._seat_map):
                for col_index, seat_id in enumerate(row):
                    if seat_id:
                        self._seat_positions[seat_id] = (row_index, col_index)
            return
        for row in range(self.rows):
            for col in range(self.cols):
                seat_id = f"r{row + 1}c{col + 1}"
                if seat_id in self._empty_seats:
                    continue
                self._seat_positions[seat_id] = (row, col)

    def seat_positions(self) -> Dict[str, Tuple[int, int]]:
        return dict(self._seat_positions)

    def available_seats(self) -> List[str]:
        return list(self._seat_positions.keys())

    def seat_position(self, seat_id: str) -> Optional[Tuple[int, int]]:
        return self._seat_positions.get(seat_id)

    def adjacency(self) -> Dict[str, List[str]]:
        neighbors: Dict[str, List[str]] = {seat_id: [] for seat_id in self._seat_positions}
        for seat_id, (row, col) in self._seat_positions.items():
            for other_id, (orow, ocol) in self._seat_positions.items():
                if seat_id == other_id:
                    continue
                if (row == orow and abs(col - ocol) == 1) or (
                    col == ocol and abs(row - orow) == 1
                ):
                    neighbors[seat_id].append(other_id)
        return neighbors

    def distance(self, seat_a: str, seat_b: str) -> Optional[int]:
        pos_a = self._seat_positions.get(seat_a)
        pos_b = self._seat_positions.get(seat_b)
        if not pos_a or not pos_b:
            return None
        return abs(pos_a[0] - pos_b[0]) + abs(pos_a[1] - pos_b[1])

    def describe(self) -> dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "empty_seats": sorted(self._empty_seats),
            "teacher_desk": dict(self.teacher_desk),
            "doors": list(self.doors),
            "seat_positions": {
                seat_id: [row, col]
                for seat_id, (row, col) in self._seat_positions.items()
            },
        }


class WorldModel:
    def __init__(
        self,
        scenes: Iterable[Scene],
        layout: Optional[ClassroomLayout],
        objects: Iterable[WorldObject],
    ) -> None:
        self._scenes: Dict[str, Scene] = {scene.scene_id: scene for scene in scenes}
        self._layout = layout
        self._objects: Dict[str, WorldObject] = {
            item.object_id: item for item in objects
        }
        self._locations: Dict[str, AgentLocation] = {}
        self._seat_positions = layout.seat_positions() if layout else {}
        self._adjacency = layout.adjacency() if layout else {}
        self._patrol_row: Optional[int] = None

    @property
    def layout(self) -> Optional[ClassroomLayout]:
        return self._layout

    def has_scene(self, scene_id: str) -> bool:
        return scene_id in self._scenes

    def snapshot(self) -> dict:
        layout = self._layout.describe() if self._layout else None
        return {
            "scenes": [
                {"id": scene.scene_id, "type": scene.scene_type}
                for scene in self._scenes.values()
            ],
            "layout": layout,
            "agents": [
                {
                    "agent_id": agent_id,
                    "scene_id": location.scene_id,
                    "seat_id": location.seat_id,
                    "row": location.row,
                    "col": location.col,
                }
                for agent_id, location in self._locations.items()
            ],
            "objects": [
                {
                    "id": obj.object_id,
                    "type": obj.object_type,
                    "state": obj.state,
                    "holder_id": obj.holder_id,
                    "owner_id": obj.owner_id,
                    "scene_id": obj.scene_id,
                }
                for obj in self._objects.values()
            ],
            "patrol_row": self._patrol_row,
        }

    def assign_seats(self, agent_ids: Iterable[str], scene_id: str = "classroom") -> None:
        if not self._layout:
            return
        seats = self._layout.available_seats()
        for agent_id, seat_id in zip(agent_ids, seats):
            row, col = self._seat_positions.get(seat_id, (None, None))
            self._locations[agent_id] = AgentLocation(
                scene_id=scene_id, seat_id=seat_id, row=row, col=col
            )

    def ensure_personal_objects(self, agent_ids: Iterable[str], types: Iterable[str]) -> None:
        for agent_id in agent_ids:
            for obj_type in types:
                object_id = f"{obj_type}.{agent_id}"
                if object_id in self._objects:
                    continue
                self._objects[object_id] = WorldObject(
                    object_id=object_id,
                    object_type=obj_type,
                    scene_id="classroom",
                    state="available",
                    owner_id=agent_id,
                )

    def location_for(self, agent_id: str) -> Optional[AgentLocation]:
        return self._locations.get(agent_id)

    def move_agent(self, agent_id: str, scene_id: str) -> None:
        current = self._locations.get(agent_id)
        seat_id = current.seat_id if current else None
        row = current.row if current else None
        col = current.col if current else None
        self._locations[agent_id] = AgentLocation(
            scene_id=scene_id, seat_id=seat_id, row=row, col=col
        )

    def move_all(self, agent_ids: Iterable[str], scene_id: str) -> None:
        for agent_id in agent_ids:
            self.move_agent(agent_id, scene_id)

    def adjacent_seats(self, seat_id: str) -> List[str]:
        return list(self._adjacency.get(seat_id, []))

    def are_adjacent(self, seat_a: str, seat_b: str) -> bool:
        return seat_b in self._adjacency.get(seat_a, [])

    def pick_peer_with_bias(
        self, agent_id: str, peers: List[str], rng, adjacency_bias: float = 0.7
    ) -> Optional[str]:
        if not peers:
            return None
        location = self._locations.get(agent_id)
        if not location or not location.seat_id:
            return rng.choice(peers) if rng else peers[0]
        adjacent_peers = []
        for peer_id in peers:
            peer_loc = self._locations.get(peer_id)
            if peer_loc and peer_loc.seat_id and self.are_adjacent(
                location.seat_id, peer_loc.seat_id
            ):
                adjacent_peers.append(peer_id)
        if adjacent_peers and rng and rng.random() < adjacency_bias:
            return rng.choice(adjacent_peers)
        if adjacent_peers and not rng and adjacency_bias >= 0.5:
            return adjacent_peers[0]
        return rng.choice(peers) if rng else peers[0]

    def set_patrol_row(self, row: Optional[int]) -> None:
        self._patrol_row = row

    def is_visible(self, agent_id: str) -> bool:
        if self._patrol_row is None:
            return False
        location = self._locations.get(agent_id)
        if not location or location.row is None:
            return False
        return location.row == self._patrol_row

    def objects_by_type(self, object_type: str) -> List[WorldObject]:
        return [obj for obj in self._objects.values() if obj.object_type == object_type]

    def borrow_object(self, object_id: str, actor_id: str, from_id: Optional[str]) -> bool:
        obj = self._objects.get(object_id)
        if not obj:
            return False
        obj.state = "borrowed"
        obj.holder_id = actor_id
        if from_id:
            obj.owner_id = from_id
        return True

    def use_object(self, object_id: str, actor_id: str) -> bool:
        obj = self._objects.get(object_id)
        if not obj:
            return False
        obj.state = "used"
        obj.holder_id = actor_id
        return True

    def return_object(self, object_id: str) -> bool:
        obj = self._objects.get(object_id)
        if not obj:
            return False
        obj.state = "available"
        obj.holder_id = None
        return True


def build_world_model(
    scenes_cfg: Iterable[dict],
    classroom_layout_cfg: Optional[dict],
    objects_cfg: Iterable[dict],
) -> WorldModel:
    scenes = [
        Scene(
            scene_id=str(item.get("id", "")),
            scene_type=str(item.get("type", "classroom")),
            layout_id=item.get("layout_id"),
        )
        for item in scenes_cfg
        if item.get("id")
    ]
    if not scenes:
        scenes = [Scene(scene_id="classroom", scene_type="classroom", layout_id="main")]
    layout = ClassroomLayout.from_config(classroom_layout_cfg or {})
    objects = [
        WorldObject(
            object_id=str(item.get("id", "")),
            object_type=str(item.get("type", "object")),
            scene_id=item.get("scene_id", "classroom"),
            state=str(item.get("state", "available")),
        )
        for item in objects_cfg
        if item.get("id")
    ]
    return WorldModel(scenes=scenes, layout=layout, objects=objects)
