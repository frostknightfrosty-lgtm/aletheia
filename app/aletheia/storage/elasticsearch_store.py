"""Elasticsearch storage backend (run manifests, graph snapshots, and search).

Graphs and manifests are indexed as JSON documents keyed by run id. Because the
store is a search engine, ``search_entities`` exposes a real capability the
other backends do not have: finding runs whose stored documents match a field
query. That is what makes this backend more than an object store.

Configuration::

    ALETHEIA_STORAGE_ELASTICSEARCH=http://localhost:9200
"""

from __future__ import annotations

from typing import Any

from aletheia.storage.base import Migration, StorageBackend
from aletheia.storage.dsn import parse_dsn

_GRAPHS_INDEX = "aletheia-graphs"
_MANIFESTS_INDEX = "aletheia-manifests"
_MIGRATIONS_INDEX = "aletheia-migrations"

_MIGRATIONS = [
    Migration(
        version=1,
        name="documents_indices",
        statement="create aletheia-graphs, aletheia-manifests and aletheia-migrations indices",
    )
]


def _is_missing(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404 or "NotFound" in type(exc).__name__


class ElasticsearchBackend(StorageBackend):
    backend_name = "elasticsearch"

    def __init__(self, url: str, *, client: Any | None = None) -> None:
        self._url = url
        self._dsn = parse_dsn(url, default_port=9200)
        self._client = client

    @classmethod
    def from_env(cls, value: str) -> "ElasticsearchBackend":
        return cls(value)

    def _es(self):
        if self._client is None:
            import elasticsearch

            self._client = elasticsearch.Elasticsearch(hosts=[self._url])
        return self._client

    # -- graph snapshots -------------------------------------------------
    def save_graph(self, run_id: str, graph: dict[str, Any]) -> str:
        self._es().index(index=_GRAPHS_INDEX, id=run_id, document={"graph": graph}, refresh="wait_for")
        return f"elasticsearch:{_GRAPHS_INDEX}/{run_id}"

    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        try:
            resp = self._es().get(index=_GRAPHS_INDEX, id=run_id)
        except Exception as exc:  # noqa: BLE001 - 404 means absent
            if _is_missing(exc):
                return None
            raise
        return resp["_source"]["graph"]

    # -- run manifests ---------------------------------------------------
    def save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        self._es().index(index=_MANIFESTS_INDEX, id=run_id, document={"manifest": manifest}, refresh="wait_for")

    def load_manifest(self, run_id: str) -> dict[str, Any] | None:
        try:
            resp = self._es().get(index=_MANIFESTS_INDEX, id=run_id)
        except Exception as exc:  # noqa: BLE001 - 404 means absent
            if _is_missing(exc):
                return None
            raise
        return resp["_source"]["manifest"]

    # -- introspection ---------------------------------------------------
    def list_runs(self) -> list[str]:
        self._es().indices.refresh(index=f"{_GRAPHS_INDEX},{_MANIFESTS_INDEX}")
        resp = self._es().search(
            index=f"{_GRAPHS_INDEX},{_MANIFESTS_INDEX}",
            query={"match_all": {}},
            size=1000,
            source=False,
        )
        return sorted({hit["_id"] for hit in resp["hits"]["hits"]})

    def search_entities(self, run_id: str, canonical_value: str) -> list[dict[str, Any]]:
        """Return entities in ``run_id`` whose canonical value matches exactly."""
        resp = self._es().search(
            index=_GRAPHS_INDEX,
            query={
                "bool": {
                    "filter": [
                        {"term": {"_id": run_id}},
                        {"nested": {"path": "graph.entities", "query": {"term": {"graph.entities.canonical_value": canonical_value}}}},
                    ]
                }
            },
            size=10,
        )
        hits = resp["hits"]["hits"]
        if not hits:
            return []
        return hits[0]["_source"]["graph"]["entities"]

    def health(self) -> dict[str, Any]:
        try:
            ok = bool(self._es().ping())
            return {"backend": self.backend_name, "ok": ok, "host": self._dsn.host, "port": self._dsn.port}
        except Exception as exc:  # noqa: BLE001 - health never raises
            return {"backend": self.backend_name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - best effort
                pass
            self._client = None

    # -- migrations ------------------------------------------------------
    def migrations(self) -> list[Migration]:
        return list(_MIGRATIONS)

    def apply_migration(self, migration: Migration) -> None:
        if migration.version != 1:
            raise ValueError(f"unknown migration version {migration.version}")
        es = self._es()
        mappings = {
            "properties": {
                "graph": {
                    "properties": {
                        "entities": {
                            "type": "nested",
                            "properties": {
                                "entity_id": {"type": "keyword"},
                                "entity_type": {"type": "keyword"},
                                "canonical_value": {"type": "keyword"},
                            },
                        }
                    }
                }
            }
        }
        for index, body in (
            (_GRAPHS_INDEX, mappings),
            (_MANIFESTS_INDEX, {"properties": {"manifest": {"properties": {"goal": {"type": "text"}}}}}),
            (_MIGRATIONS_INDEX, {}),
        ):
            if not es.indices.exists(index=index):
                es.indices.create(index=index, mappings=body)

    def applied_migrations(self) -> list[dict[str, Any]]:
        es = self._es()
        if not es.indices.exists(index=_MIGRATIONS_INDEX):
            return []
        es.indices.refresh(index=_MIGRATIONS_INDEX)
        resp = es.search(index=_MIGRATIONS_INDEX, query={"match_all": {}}, size=100)
        rows = [hit["_source"] for hit in resp["hits"]["hits"]]
        return sorted(
            (
                {
                    "version": int(row["version"]),
                    "name": row["name"],
                    "checksum": row["checksum"],
                    "applied_at": row["applied_at"],
                }
                for row in rows
            ),
            key=lambda row: row["version"],
        )

    def record_migration(self, applied: dict[str, Any]) -> None:
        self._es().index(
            index=_MIGRATIONS_INDEX, id=str(applied["version"]), document=applied, refresh="wait_for"
        )
