from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    config_path: Path
    data_path: Path


def resolve_paths() -> AppPaths:
    root = Path(__file__).resolve().parents[3]
    config_path = root / "configs" / "campus_basic.json"
    data_path = root / "data" / "sim.db"
    return AppPaths(root=root, config_path=config_path, data_path=data_path)
