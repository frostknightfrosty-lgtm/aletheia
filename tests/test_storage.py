"""Storage backend unit tests (no external service required).

Covers the migration runner, the file backend, the factory, the Redis backend
(via ``fakeredis``), and — importantly — a *negative control* proving the shared
conformance contract actually fails on a broken backend.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aletheia.storage import BACKENDS, ENV_VARS, NETWORKED_BACKENDS, open_backend
from aletheia.storage.base import Migration, MigrationError, MigrationRunner, StorageBackend
from aletheia.storage.conformance import SAMPLE_GRAPH, SAMPLE_MANIFEST, conform
from aletheia.storage.file_store import FileGraphStore
from aletheia.storage.redis_store import RedisBackend


class FakeBackend(StorageBackend):
    """In-memory backend used to unit-test the runner and conformance harness."""

    backend_name = "fake"

    def __init__(self) -> None:
        self.graphs: dict[str, dict[str, Any]] = {}
        self.manifests: dict[str, dict[str, Any]] = {}
        self._migrations: list[dict[str, Any]] = []
        self.applied: list[int] = []
        self.calls: list[str] = []

    def save_graph(self, run_id: str, graph: dict[str, Any]) -> str:
        self.graphs[run_id] = graph
        return f"fake:graph/{run_id}"

    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        return self.graphs.get(run_id)

    def save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        self.manifests[run_id] = manifest

    def load_manifest(self, run_id: str) -> dict[str, Any] | None:
        return self.manifests.get(run_id)

    def list_runs(self) -> list[str]:
        return sorted(set(self.graphs) | set(self.manifests))

    def health(self) -> dict[str, Any]:
        return {"backend": self.backend_name, "ok": True}

    def migrations(self) -> list[Migration]:
        return [Migration(version=1, name="first", statement="a"), Migration(version=2, name="second", statement="b")]

    def prepare_migrations(self) -> None:
        self.calls.append("prepare")

    def apply_migration(self, migration: Migration) -> None:
        self.applied.append(migration.version)

    def applied_migrations(self) -> list[dict[str, Any]]:
        self.calls.append("applied")
        return list(self._migrations)

    def record_migration(self, applied: dict[str, Any]) -> None:
        self._migrations = [row for row in self._migrations if row["version"] != applied["version"]]
        self._migrations.append(applied)
        self._migrations.sort(key=lambda row: row["version"])

    def verify_materialised(self, run_id: str, entities: int, edges: int) -> dict[str, int]:
        graph = self.graphs.get(run_id, {"entities": [], "edges": []})
        observed = {"entities": len(graph.get("entities", [])), "edges": len(graph.get("edges", []))}
        if observed != {"entities": entities, "edges": edges}:
            raise AssertionError(f"materialised mismatch: {observed} != entities={entities} edges={edges}")
        return observed


def test_migration_runner_applies_in_order_once(tmp_path: Path) -> None:
    backend = FakeBackend()
    runner = MigrationRunner(backend)

    assert runner.status()["pending"] == [1, 2]
    first = runner.run()
    assert first["applied_now"] == [1, 2]
    assert backend.applied == [1, 2]

    second = runner.run()
    assert second["applied_now"] == []
    assert backend.applied == [1, 2]
    assert [row["version"] for row in backend.applied_migrations()] == [1, 2]


def test_migration_runner_prepares_backend_before_reading_recorded_state() -> None:
    """The runner must create its bookkeeping before it queries it.

    Run 39079850431 failed ``migrate`` on PostgreSQL with
    ``relation "aletheia_schema_migrations" does not exist``: the log table was
    created by migration 1, but the runner reads that table before it applies
    anything. No file-backed test could see the ordering, so this pins it.
    """
    backend = FakeBackend()
    MigrationRunner(backend).run()
    assert backend.calls[:2] == ["prepare", "applied"], backend.calls
    assert backend.applied == [1, 2]


def test_migration_runner_status_also_prepares_the_backend() -> None:
    backend = FakeBackend()
    MigrationRunner(backend).status()
    assert backend.calls[:2] == ["prepare", "applied"], backend.calls


def test_migration_runner_detects_checksum_drift() -> None:
    backend = FakeBackend()
    MigrationRunner(backend).run()

    # Mutate the recorded checksum: the runner must refuse to continue silently.
    backend._migrations[0]["checksum"] = "0" * 64
    with pytest.raises(MigrationError, match="checksum drift"):
        MigrationRunner(backend).run()


def test_migration_runner_detects_name_drift() -> None:
    backend = FakeBackend()
    MigrationRunner(backend).run()
    backend._migrations[0]["name"] = "renamed"
    with pytest.raises(MigrationError, match="name drift"):
        MigrationRunner(backend).run()


def test_conformance_passes_for_file_backend(tmp_path: Path) -> None:
    result = conform(FileGraphStore(tmp_path / "graphs"))
    assert result["ok"] is True, json.dumps(result, indent=2)
    names = {check["name"] for check in result["checks"]}
    assert {"health", "migrate", "migrate_idempotent", "graph_round_trip", "manifest_round_trip"} <= names
    assert all(check["ok"] for check in result["checks"])


def test_conformance_passes_for_fake_backend() -> None:
    assert conform(FakeBackend())["ok"] is True


def test_materialisation_hook_is_exercised_and_can_fail() -> None:
    result = conform(FakeBackend())
    checks = {check["name"]: check for check in result["checks"]}
    # The hook must actually run (not "n/a") and must track both the populated
    # graph and the replacement written by the overwrite check.
    assert checks["graph_materialised"]["detail"] == "entities=2 edges=1"
    assert checks["overwrite_materialised"]["detail"] == "entities=0 edges=0"

    class BadMaterialisation(FakeBackend):
        def verify_materialised(self, run_id: str, entities: int, edges: int) -> dict[str, int]:
            return {"entities": entities, "edges": edges + 1}

    bad = conform(BadMaterialisation())
    assert bad["ok"] is False
    assert any(check["name"] == "graph_materialised" and not check["ok"] for check in bad["checks"])


class BrokenBackend(FakeBackend):
    """Returns a wrong graph for stored runs: the contract must catch this."""

    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        stored = super().load_graph(run_id)
        if stored is None:
            return None
        return {"entities": [], "edges": []}


def test_conformance_fails_for_broken_backend() -> None:
    result = conform(BrokenBackend())
    assert result["ok"] is False
    failed = [check["name"] for check in result["checks"] if not check["ok"] and not check.get("skipped")]
    assert "graph_round_trip" in failed


def test_conformance_passes_for_redis_backend_against_fakeredis() -> None:
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.FakeStrictRedis(decode_responses=True)
    backend = RedisBackend("redis://localhost:6379/0", client=client)
    result = conform(backend)
    assert result["ok"] is True, json.dumps(result, indent=2)
    # The Redis backend must namespace every key it owns.
    assert all(key.startswith("aletheia:") for key in client.keys("*"))


def test_file_backend_round_trips_and_lists(tmp_path: Path) -> None:
    store = FileGraphStore(tmp_path)
    store.save_graph("run-a", SAMPLE_GRAPH)
    store.save_manifest("run-a", SAMPLE_MANIFEST)
    store.save_graph("run-b", {"entities": [], "edges": []})

    assert store.load_graph("run-a") == SAMPLE_GRAPH
    assert store.load_manifest("run-a") == SAMPLE_MANIFEST
    assert store.list_runs() == ["run-a", "run-b"]
    assert store.load_graph("missing") is None
    assert store.health()["ok"] is True


def test_file_backend_migration_state_persists(tmp_path: Path) -> None:
    root = tmp_path / "graphs"
    FileGraphStore(root)
    MigrationRunner(FileGraphStore(root)).run()

    reopened = FileGraphStore(root)
    assert [row["version"] for row in reopened.applied_migrations()] == [1]
    assert MigrationRunner(reopened).status()["pending"] == []


def test_open_backend_factory(tmp_path: Path) -> None:
    assert isinstance(open_backend("file", str(tmp_path)), FileGraphStore)
    with pytest.raises(ValueError, match="unknown storage backend"):
        open_backend("cassandra", "x")


def test_registry_covers_every_declared_backend() -> None:
    assert set(NETWORKED_BACKENDS) <= set(BACKENDS)
    assert set(ENV_VARS) == set(NETWORKED_BACKENDS)


def _seed_run(data_dir: Path, run_id: str) -> dict[str, Any]:
    (data_dir / "graphs" / run_id).mkdir(parents=True)
    (data_dir / "runs" / run_id).mkdir(parents=True)
    graph = {"entities": [{"entity_id": "1", "entity_type": "username", "canonical_value": "x", "attributes": {}}], "edges": []}
    manifest = {"goal": "cli smoke", "chain_tip": "0" * 64}
    (data_dir / "graphs" / run_id / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (data_dir / "runs" / run_id / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return graph


def test_health_report_marks_unconfigured_backends(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aletheia.storage import health_report

    # Deterministic in every environment on purpose. The first version of this
    # test read whatever the machine happened to have exported, so it failed in
    # CI (run 39079850431), where every backend variable is set.
    for var in ENV_VARS.values():
        monkeypatch.delenv(var, raising=False)

    report = health_report(data_dir=tmp_path)
    assert report["file"]["ok"] is True
    assert report["file"]["configured"] is True
    for name in NETWORKED_BACKENDS:
        assert report[name]["configured"] is False
        assert report[name]["detail"] == "env var not set"


def test_health_report_marks_a_configured_but_unreachable_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aletheia.storage import health_report

    # Port 1 on loopback has no listener: the backend is configured, so it must
    # be probed and reported unhealthy rather than quietly skipped.
    monkeypatch.setenv("ALETHEIA_STORAGE_POSTGRES", "postgresql://u:p@127.0.0.1:1/db")

    report = health_report(["postgres"], data_dir=tmp_path)
    assert report["postgres"]["configured"] is True
    assert report["postgres"]["ok"] is False
    assert report["postgres"]["detail"]


def test_postgres_health_accepts_driver_rows_typed_as_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    """pg8000 appends every row as a Python ``list``, so ``[[1]] != [(1,)]``.

    Run 39079850431 reported a perfectly healthy PostgreSQL as unreachable
    because ``health`` compared the driver's rows against a literal tuple. This
    reproduces the driver's exact row shape without needing a server.
    """
    from aletheia.storage.postgres_store import PostgresBackend

    class _Cursor:
        def execute(self, sql: str, params: tuple = ()) -> None:
            self.sql = sql

        def fetchall(self):
            return ([1],)  # pg8000/core.py handle_DATA_ROW builds lists

        def close(self) -> None:
            pass

    class _Conn:
        autocommit = False

        def cursor(self) -> _Cursor:
            return _Cursor()

        def commit(self) -> None:
            pass

    backend = PostgresBackend("postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setattr(backend, "_connection", lambda: _Conn())

    health = backend.health()
    assert health["ok"] is True, health
    assert "SELECT 1" in health["detail"]


def test_postgres_health_reports_connection_failure_with_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from aletheia.storage.postgres_store import PostgresBackend

    backend = PostgresBackend("postgresql://u:p@127.0.0.1:5432/db")

    def _refuse():
        raise OSError("connection refused")

    monkeypatch.setattr(backend, "_connection", _refuse)

    health = backend.health()
    assert health["ok"] is False
    assert "connection refused" in health["detail"]
    # The first CI failure printed no host/port, which made the diagnosis
    # harder than it needed to be.
    assert health["host"] == "127.0.0.1"
    assert health["port"] == 5432


def test_sync_run_mirrors_graph_and_manifest(tmp_path: Path) -> None:
    from aletheia.storage import sync_run

    run_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    graph = _seed_run(tmp_path, run_id)
    mirror = FileGraphStore(tmp_path / "mirror")

    result = sync_run(mirror, run_id, tmp_path)
    assert result["verified"] is True
    assert result["synced"] == ["graph", "manifest"]
    assert "migrations" in result
    assert mirror.load_graph(run_id) == graph
    assert mirror.load_manifest(run_id)["goal"] == "cli smoke"


def test_sync_run_applies_the_backends_migrations_first(tmp_path: Path) -> None:
    """Syncing into a brand-new backend must create its schema.

    Before this, ``aletheia storage sync`` into a fresh PostgreSQL failed with
    "relation does not exist" unless the operator happened to run
    ``storage migrate`` first.
    """
    from aletheia.storage import sync_run

    run_id = "cccccccc-dddd-eeee-ffff-000000000000"
    _seed_run(tmp_path, run_id)
    mirror = FakeBackend()

    result = sync_run(mirror, run_id, tmp_path)

    assert mirror.applied == [1, 2], mirror.calls
    assert result["migrations"] == [1, 2]
    assert result["verified"] is True


def test_storage_cli_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    from aletheia.cli.main import main

    run_id = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
    _seed_run(tmp_path, run_id)

    def invoke(*argv: str) -> dict[str, Any]:
        monkeypatch.setattr("sys.argv", ["aletheia", "storage", *argv])
        main()
        return json.loads(capsys.readouterr().out)

    assert invoke("health", "--backend", "file", "--data-dir", str(tmp_path))["file"]["ok"] is True
    assert invoke("migrate", "--backend", "file", "--data-dir", str(tmp_path))["applied_now"] == [1]
    sync = invoke(
        "sync",
        "--run-id",
        run_id,
        "--backend",
        "file",
        "--target",
        str(tmp_path / "mirror2"),
        "--data-dir",
        str(tmp_path),
    )
    assert sync["verified"] is True and sync["synced"] == ["graph", "manifest"]
