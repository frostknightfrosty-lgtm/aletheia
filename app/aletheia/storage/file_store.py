from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aletheia.storage.base import Migration, StorageBackend

# The file backend's "schema" is the on-disk layout under a single root: one
# directory per run holding graph.json and MANIFEST.json. The migration is
# recorded so the migration runner has a uniform story across backends, and it
# only asserts the root exists (which the constructor already guarantees).
_LAYOUT_MIGRATION = Migration(
    version=1,
    name="run_directory_layout",
    statement="ensure <root> exists and holds <run_id>/graph.json + <run_id>/MANIFEST.json",
)


class FileGraphStore(StorageBackend):
    """Phase-1 deterministic store for local execution/tests.

    Implements the Phase-14 :class:`~aletheia.storage.base.StorageBackend`
    contract so the same conformance suite that guards PostgreSQL, Neo4j,
    Elasticsearch, MinIO and Redis also guards the default file store. The
    ``root`` attribute is retained because the API and orchestrator address
    ``<root>/<run_id>/graph.json`` directly.
    """

    backend_name = "file"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths -----------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        return self.root / str(run_id)

    def graph_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "graph.json"

    def manifest_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "MANIFEST.json"

    # -- graph snapshots -------------------------------------------------
    def save_graph(self, run_id: str, graph: dict[str, Any]) -> str:
        path = self.graph_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(graph, indent=2, sort_keys=True), encoding="utf-8")
        return str(path)

    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        path = self.graph_path(run_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # -- run manifests ---------------------------------------------------
    def save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        path = self.manifest_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    def load_manifest(self, run_id: str) -> dict[str, Any] | None:
        path = self.manifest_path(run_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # -- introspection ---------------------------------------------------
    def list_runs(self) -> list[str]:
        runs = []
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            if self.graph_path(child.name).exists() or self.manifest_path(child.name).exists():
                runs.append(child.name)
        return sorted(runs)

    def health(self) -> dict[str, Any]:
        try:
            writable = self.root.is_dir()
        except OSError as exc:  # pragma: no cover - defensive
            return {"backend": self.backend_name, "ok": False, "detail": str(exc)}
        return {"backend": self.backend_name, "ok": writable, "root": str(self.root)}

    # -- migrations ------------------------------------------------------
    def migrations(self) -> list[Migration]:
        return [_LAYOUT_MIGRATION]

    def apply_migration(self, migration: Migration) -> None:
        if migration.version == _LAYOUT_MIGRATION.version:
            self.root.mkdir(parents=True, exist_ok=True)
            return
        raise ValueError(f"unknown migration version {migration.version}")

    def _schema_path(self) -> Path:
        return self.root / ".aletheia_schema.json"

    def applied_migrations(self) -> list[dict[str, Any]]:
        path = self._schema_path()
        if not path.exists():
            return []
        try:
            recorded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(recorded, list):
            return []
        return recorded

    def record_migration(self, applied: dict[str, Any]) -> None:
        recorded = [row for row in self.applied_migrations() if int(row["version"]) != int(applied["version"])]
        recorded.append(applied)
        recorded.sort(key=lambda row: int(row["version"]))
        self._schema_path().write_text(json.dumps(recorded, indent=2, sort_keys=True), encoding="utf-8")
