"""Storage backend interfaces and the schema-migration runner.

Phase 14 introduces one narrow, JSON-oriented persistence contract that every
backend (file, PostgreSQL, Neo4j, Elasticsearch, MinIO, Redis) implements, plus
a migration runner that applies an ordered set of migrations exactly once and
records what it applied.

The contract deliberately stores whole JSON documents rather than trying to
normalise entities/edges into a universal schema. A graph database backend may
*additionally* materialise entities and edges (Neo4j does), but the round-trip
contract that the conformance suite proves is the JSON snapshot, so a graph
exported by the pipeline can be replayed byte-for-byte through any backend.

This module is pure standard library so it can be imported and tested without
any network service or third-party driver installed.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Migration:
    """One ordered, checksum-verified schema migration for a backend.

    ``statement`` is a single statement or a sequence of statements to apply in
    order (Postgres DDL, Cypher constraints, ...).
    """

    version: int
    name: str
    statement: str | tuple[str, ...]

    @property
    def statements(self) -> tuple[str, ...]:
        return (self.statement,) if isinstance(self.statement, str) else tuple(self.statement)

    @property
    def checksum(self) -> str:
        joined = "\x00".join(self.statements)
        payload = f"{self.version}\x00{self.name}\x00{joined}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class MigrationError(RuntimeError):
    """Raised when the migration runner detects drift or out-of-order state."""


class StorageBackend(ABC):
    """JSON document persistence for graph snapshots and run manifests.

    Implementations must be safe to construct without a reachable server; the
    first operation that needs the server may raise, and ``health`` must report
    reachability without raising.
    """

    backend_name: ClassVar[str] = "abstract"

    # -- graph snapshots -------------------------------------------------
    @abstractmethod
    def save_graph(self, run_id: str, graph: dict[str, Any]) -> str:
        """Persist ``graph`` for ``run_id``; return a backend-local locator."""

    @abstractmethod
    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        """Return the stored graph for ``run_id`` or ``None`` when absent."""

    # -- run manifests ---------------------------------------------------
    @abstractmethod
    def save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        """Persist ``manifest`` for ``run_id``, replacing any previous value."""

    @abstractmethod
    def load_manifest(self, run_id: str) -> dict[str, Any] | None:
        """Return the stored manifest for ``run_id`` or ``None`` when absent."""

    # -- introspection ---------------------------------------------------
    @abstractmethod
    def list_runs(self) -> list[str]:
        """Return the sorted run ids that have a graph or a manifest."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return ``{"backend", "ok", ...}`` without raising on failure."""

    def close(self) -> None:  # pragma: no cover - default no-op
        """Release any held connection. Safe to call more than once."""

    # -- migrations ------------------------------------------------------
    def migrations(self) -> list[Migration]:
        """Return this backend's migrations, ordered by version."""
        return []

    @abstractmethod
    def apply_migration(self, migration: Migration) -> None:
        """Apply a single migration's effect idempotently."""

    @abstractmethod
    def applied_migrations(self) -> list[dict[str, Any]]:
        """Return recorded migrations as ``version/name/checksum/applied_at``."""

    @abstractmethod
    def record_migration(self, applied: dict[str, Any]) -> None:
        """Persist one recorded migration (idempotent on ``version``)."""


class MigrationRunner:
    """Apply every pending migration once and verify already-applied checksums."""

    def __init__(self, backend: StorageBackend) -> None:
        self.backend = backend

    def status(self) -> dict[str, Any]:
        recorded = {int(row["version"]): row for row in self.backend.applied_migrations()}
        pending = [m.version for m in self.backend.migrations() if m.version not in recorded]
        return {
            "backend": self.backend.backend_name,
            "applied": sorted(recorded),
            "pending": sorted(pending),
        }

    def run(self) -> dict[str, Any]:
        recorded = {int(row["version"]): row for row in self.backend.applied_migrations()}
        planned = sorted(self.backend.migrations(), key=lambda m: m.version)
        applied_now: list[int] = []

        for migration in planned:
            existing = recorded.get(migration.version)
            if existing is not None:
                if existing.get("checksum") != migration.checksum:
                    raise MigrationError(
                        f"migration {migration.version} ({migration.name}) checksum drift: "
                        f"recorded {existing.get('checksum')!r} != planned {migration.checksum!r}"
                    )
                if existing.get("name") != migration.name:
                    raise MigrationError(
                        f"migration {migration.version} name drift: "
                        f"recorded {existing.get('name')!r} != planned {migration.name!r}"
                    )
                continue
            self.backend.apply_migration(migration)
            self.backend.record_migration(
                {
                    "version": migration.version,
                    "name": migration.name,
                    "checksum": migration.checksum,
                    "applied_at": utc_now_iso(),
                }
            )
            applied_now.append(migration.version)

        return {
            "backend": self.backend.backend_name,
            "applied_now": sorted(applied_now),
            "applied_total": sorted(recorded) + sorted(applied_now),
        }
