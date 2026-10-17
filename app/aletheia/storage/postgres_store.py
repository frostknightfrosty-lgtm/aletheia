"""PostgreSQL storage backend (run manifests and graph snapshots).

Uses ``pg8000.dbapi`` (a pure-Python DB-API 2.0 driver) so the backend has no
C-extension build requirement. Two tables hold JSONB documents keyed by run id
and a third records applied schema migrations.

Configuration::

    ALETHEIA_STORAGE_POSTGRES=postgresql://user:pass@host:5432/dbname
"""

from __future__ import annotations

import json
from typing import Any

from aletheia.storage.base import Migration, StorageBackend
from aletheia.storage.dsn import parse_dsn

_MIGRATIONS = [
    Migration(
        version=1,
        name="jsonb_documents",
        statement=(
            "CREATE TABLE IF NOT EXISTS aletheia_graphs ("
            " run_id text PRIMARY KEY, payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())",
            "CREATE TABLE IF NOT EXISTS aletheia_manifests ("
            " run_id text PRIMARY KEY, payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())",
            "CREATE TABLE IF NOT EXISTS aletheia_schema_migrations ("
            " version integer PRIMARY KEY, name text NOT NULL, checksum text NOT NULL, applied_at text NOT NULL)",
        ),
    )
]


def _as_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


class PostgresBackend(StorageBackend):
    backend_name = "postgres"

    def __init__(self, url: str) -> None:
        dsn = parse_dsn(url, default_port=5432)
        self._dsn = dsn
        self._conn = None

    @classmethod
    def from_env(cls, value: str) -> "PostgresBackend":
        return cls(value)

    def _connection(self):
        if self._conn is None:
            import pg8000.dbapi as dbapi

            kwargs: dict[str, Any] = {
                "user": self._dsn.username,
                "password": self._dsn.password,
                "host": self._dsn.host,
                "port": self._dsn.port,
            }
            if self._dsn.database:
                kwargs["database"] = self._dsn.database
            self._conn = dbapi.connect(**kwargs)
            self._conn.autocommit = False
        return self._conn

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            conn.commit()
        finally:
            cur.close()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple]:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            return list(cur.fetchall())
        finally:
            cur.close()

    # -- graph snapshots -------------------------------------------------
    def save_graph(self, run_id: str, graph: dict[str, Any]) -> str:
        self._execute(
            "INSERT INTO aletheia_graphs (run_id, payload, updated_at) VALUES (%s, %s::jsonb, now())"
            " ON CONFLICT (run_id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()",
            (run_id, json.dumps(graph)),
        )
        return f"postgres:aletheia_graphs/{run_id}"

    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        rows = self._fetchall("SELECT payload FROM aletheia_graphs WHERE run_id = %s", (run_id,))
        return _as_dict(rows[0][0]) if rows else None

    # -- run manifests ---------------------------------------------------
    def save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        self._execute(
            "INSERT INTO aletheia_manifests (run_id, payload, updated_at) VALUES (%s, %s::jsonb, now())"
            " ON CONFLICT (run_id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()",
            (run_id, json.dumps(manifest)),
        )

    def load_manifest(self, run_id: str) -> dict[str, Any] | None:
        rows = self._fetchall("SELECT payload FROM aletheia_manifests WHERE run_id = %s", (run_id,))
        return _as_dict(rows[0][0]) if rows else None

    # -- introspection ---------------------------------------------------
    def list_runs(self) -> list[str]:
        rows = self._fetchall(
            "SELECT run_id FROM ("
            " SELECT run_id FROM aletheia_graphs UNION SELECT run_id FROM aletheia_manifests"
            ") AS runs ORDER BY run_id"
        )
        return [str(row[0]) for row in rows]

    def health(self) -> dict[str, Any]:
        try:
            rows = self._fetchall("SELECT 1")
            return {
                "backend": self.backend_name,
                "ok": rows == [(1,)],
                "host": self._dsn.host,
                "port": self._dsn.port,
            }
        except Exception as exc:  # noqa: BLE001 - health never raises
            return {"backend": self.backend_name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    # -- migrations ------------------------------------------------------
    def migrations(self) -> list[Migration]:
        return list(_MIGRATIONS)

    def apply_migration(self, migration: Migration) -> None:
        for statement in migration.statement:
            self._execute(statement)

    def applied_migrations(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT version, name, checksum, applied_at FROM aletheia_schema_migrations ORDER BY version"
        )
        return [
            {"version": row[0], "name": row[1], "checksum": row[2], "applied_at": row[3]} for row in rows
        ]

    def record_migration(self, applied: dict[str, Any]) -> None:
        self._execute(
            "INSERT INTO aletheia_schema_migrations (version, name, checksum, applied_at)"
            " VALUES (%s, %s, %s, %s) ON CONFLICT (version) DO UPDATE SET"
            " name = EXCLUDED.name, checksum = EXCLUDED.checksum, applied_at = EXCLUDED.applied_at",
            (applied["version"], applied["name"], applied["checksum"], applied["applied_at"]),
        )
