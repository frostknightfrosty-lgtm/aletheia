"""Redis storage backend (run manifests and graph snapshots).

Redis is the fastest backend here but the weakest durability story: it is a
key/value cache whose persistence depends on the server's RDB/AOF settings. It
is therefore documented as a *cache/fast-path* backend, not a system of record.
The backend namespaces every key under ``aletheia:`` and stores documents as
UTF-8 JSON.

Configuration::

    ALETHEIA_STORAGE_REDIS=redis://localhost:6379/0

The constructor accepts an injected ``client`` so the backend can be exercised
against ``fakeredis`` without a server.
"""

from __future__ import annotations

import json
from typing import Any

from aletheia.storage.base import Migration, StorageBackend
from aletheia.storage.dsn import parse_dsn

_GRAPH_PREFIX = "aletheia:graph:"
_MANIFEST_PREFIX = "aletheia:manifest:"
_MIGRATION_KEY = "aletheia:schema:migrations"

_MIGRATIONS = [
    Migration(
        version=1,
        name="key_namespace",
        statement="reserve the aletheia:{graph,manifest}:<run_id> key namespace (Redis is schema-less)",
    )
]


class RedisBackend(StorageBackend):
    backend_name = "redis"

    def __init__(self, url: str, *, client: Any | None = None) -> None:
        self._url = url
        self._dsn = parse_dsn(url, default_port=6379)
        self._client = client

    @classmethod
    def from_env(cls, value: str) -> "RedisBackend":
        return cls(value)

    def _redis(self):
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(self._url, decode_responses=True)
        return self._client

    # -- graph snapshots -------------------------------------------------
    def save_graph(self, run_id: str, graph: dict[str, Any]) -> str:
        self._redis().set(_GRAPH_PREFIX + run_id, json.dumps(graph))
        return _GRAPH_PREFIX + run_id

    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        raw = self._redis().get(_GRAPH_PREFIX + run_id)
        return json.loads(raw) if raw is not None else None

    # -- run manifests ---------------------------------------------------
    def save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        self._redis().set(_MANIFEST_PREFIX + run_id, json.dumps(manifest))

    def load_manifest(self, run_id: str) -> dict[str, Any] | None:
        raw = self._redis().get(_MANIFEST_PREFIX + run_id)
        return json.loads(raw) if raw is not None else None

    # -- introspection ---------------------------------------------------
    def _scan(self, pattern: str) -> list[str]:
        client = self._redis()
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = client.scan(cursor=cursor, match=pattern, count=500)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys

    def list_runs(self) -> list[str]:
        runs = set()
        for prefix, pattern in ((_GRAPH_PREFIX, _GRAPH_PREFIX + "*"), (_MANIFEST_PREFIX, _MANIFEST_PREFIX + "*")):
            for key in self._scan(pattern):
                runs.add(key[len(prefix):])
        return sorted(runs)

    def health(self) -> dict[str, Any]:
        try:
            ok = bool(self._redis().ping())
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

    def applied_migrations(self) -> list[dict[str, Any]]:
        raw = self._redis().hgetall(_MIGRATION_KEY)
        return [json.loads(value) for _, value in sorted(raw.items())]

    def record_migration(self, applied: dict[str, Any]) -> None:
        self._redis().hset(_MIGRATION_KEY, str(applied["version"]), json.dumps(applied))
