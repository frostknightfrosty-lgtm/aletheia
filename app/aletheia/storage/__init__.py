"""Storage backend registry and factory.

Phase 14 backends, all implementing
:class:`~aletheia.storage.base.StorageBackend`:

===============  ==================================================  ============
name             role                                                durable
===============  ==================================================  ============
``file``         default local store (``<root>/<run_id>/*.json``)     yes
``postgres``     JSONB document tables                               yes
``neo4j``        JSON snapshot + native entity/edge materialisation  yes
``elasticsearch``indexed documents + field search                    yes
``minio``        one JSON object per run in S3 buckets               yes
``redis``        namespaced key/value cache                          server-dependent
===============  ==================================================  ============

Each networked backend reads its connection string from an environment variable
(see :data:`ENV_VARS`). ``configured_backends`` returns only the backends whose
variable is set, which is what the conformance suite and the CLI iterate over.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import UUID

from aletheia.storage.base import Migration, MigrationError, MigrationRunner, StorageBackend
from aletheia.storage.elasticsearch_store import ElasticsearchBackend
from aletheia.storage.file_store import FileGraphStore
from aletheia.storage.minio_store import MinioBackend
from aletheia.storage.neo4j_store import Neo4jBackend
from aletheia.storage.postgres_store import PostgresBackend
from aletheia.storage.redis_store import RedisBackend

FILE_BACKEND = "file"

NETWORKED_BACKENDS = ("postgres", "neo4j", "elasticsearch", "minio", "redis")

ENV_VARS = {
    "postgres": "ALETHEIA_STORAGE_POSTGRES",
    "neo4j": "ALETHEIA_STORAGE_NEO4J",
    "elasticsearch": "ALETHEIA_STORAGE_ELASTICSEARCH",
    "minio": "ALETHEIA_STORAGE_MINIO",
    "redis": "ALETHEIA_STORAGE_REDIS",
}

_FACTORIES = {
    "postgres": PostgresBackend,
    "neo4j": Neo4jBackend,
    "elasticsearch": ElasticsearchBackend,
    "minio": MinioBackend,
    "redis": RedisBackend,
}

BACKENDS = {FILE_BACKEND: FileGraphStore, **_FACTORIES}

__all__ = [
    "BACKENDS",
    "ENV_VARS",
    "FILE_BACKEND",
    "NETWORKED_BACKENDS",
    "Migration",
    "MigrationError",
    "MigrationRunner",
    "StorageBackend",
    "backend_from_env",
    "configured_backends",
    "health_report",
    "open_backend",
    "resolve_backend",
    "sync_run",
]


def open_backend(name: str, target: str) -> StorageBackend:
    """Construct a backend by name.

    ``target`` is a filesystem root for ``file`` and a DSN URL for the others.
    """
    if name == FILE_BACKEND:
        return FileGraphStore(Path(target))
    try:
        factory = _FACTORIES[name]
    except KeyError as exc:
        raise ValueError(f"unknown storage backend {name!r}; known: {sorted(BACKENDS)}") from exc
    return factory(target)


def resolve_backend(name: str, data_dir: Path, target: str | None = None) -> StorageBackend:
    """Resolve a backend from an explicit target, its env var, or the data dir.

    The file backend defaults to ``<data_dir>/graphs`` (where the orchestrator
    writes); a networked backend requires an explicit ``target`` or its env var.
    """
    if target:
        return open_backend(name, target)
    if name == FILE_BACKEND:
        return open_backend(FILE_BACKEND, str(Path(data_dir) / "graphs"))
    env_var = ENV_VARS.get(name)
    value = os.environ.get(env_var) if env_var else None
    if not value:
        raise SystemExit(f"backend {name!r} needs --target or {env_var}")
    return open_backend(name, value)


def configured_backends() -> dict[str, str]:
    """Return ``{backend_name: dsn}`` for every backend whose env var is set."""
    return {name: os.environ[var] for name, var in ENV_VARS.items() if os.environ.get(var)}


def backend_from_env(name: str) -> StorageBackend | None:
    """Return a backend for ``name`` if its env var is set, else ``None``."""
    value = os.environ.get(ENV_VARS[name])
    return open_backend(name, value) if value else None


def health_report(names: list[str] | None = None, *, data_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Probe the file backend (and every requested/configured networked backend).

    A networked backend whose env var is not set is reported as ``configured:
    False`` rather than being silently omitted, so an operator can see the gap.
    """
    report: dict[str, dict[str, Any]] = {}
    for name in names if names is not None else [FILE_BACKEND, *NETWORKED_BACKENDS]:
        if name == FILE_BACKEND:
            backend = FileGraphStore(Path(data_dir or ".") / "graphs")
        else:
            value = os.environ.get(ENV_VARS[name])
            if not value:
                report[name] = {"backend": name, "ok": False, "configured": False, "detail": "env var not set"}
                continue
            backend = open_backend(name, value)
        try:
            entry = dict(backend.health())
        finally:
            backend.close()
        entry["configured"] = True
        report[name] = entry
    return report


def sync_run(backend: StorageBackend, run_id: str | UUID, data_dir: Path) -> dict[str, Any]:
    """Copy a run's graph and manifest from the file store into ``backend``.

    The file store stays authoritative; this mirrors the two JSON documents the
    backend contract covers. The backend's migrations are applied first, so
    syncing into a brand-new database works without a separate migrate step. A
    round-trip read-back is asserted before returning.
    """
    from aletheia.core.checkpoint import CheckpointStore

    run = str(run_id)
    files = FileGraphStore(Path(data_dir) / "graphs")
    checkpoints = CheckpointStore(Path(data_dir) / "runs")

    graph = files.load_graph(run)
    manifest = checkpoints.load(UUID(run))
    if graph is None and manifest is None:
        raise SystemExit(f"run {run} has no graph or manifest under {data_dir}")

    migrations = MigrationRunner(backend).run()

    synced: list[str] = []
    if graph is not None:
        backend.save_graph(run, graph)
        synced.append("graph")
    if manifest is not None:
        backend.save_manifest(run, manifest)
        synced.append("manifest")

    result = {
        "backend": backend.backend_name,
        "run_id": run,
        "synced": synced,
        "migrations": migrations["applied_now"],
        "verified": False,
    }
    if graph is not None:
        result["verified"] = backend.load_graph(run) == graph
    elif manifest is not None:
        result["verified"] = backend.load_manifest(run) == manifest
    return result

