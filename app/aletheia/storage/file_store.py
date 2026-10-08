from __future__ import annotations

import json
from pathlib import Path

from aletheia.core.models import Entity, Edge


class FileGraphStore:
    """Phase-1 deterministic store for local execution/tests; replaceable with PostgreSQL/Neo4j backends."""
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save_graph(self, run_id: str, graph: dict) -> Path:
        path = self.root / run_id / "graph.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(graph, indent=2, sort_keys=True), encoding="utf-8")
        return path
