"""Backend-agnostic conformance contract for storage backends.

One function, :func:`conform`, exercises every operation in the
:class:`~aletheia.storage.base.StorageBackend` contract against a backend
instance and returns a machine-readable record of each check. It is used both
by the pytest conformance suite (``tests/test_storage_conformance.py``) and by
the CI evidence script (``ci/storage_conformance.py``) so the two can never
drift apart.

Only the standard library is imported here, so the contract itself is provable
locally against the file backend with no service running.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from aletheia.storage.base import MigrationRunner, StorageBackend

# A graph payload that stresses the parts of the contract most likely to break:
# nested objects, a unicode canonical value, and an empty list.
SAMPLE_GRAPH: dict[str, Any] = {
    "entities": [
        {
            "entity_id": "11111111-1111-1111-1111-111111111111",
            "entity_type": "username",
            "canonical_value": "sn\u00f6b\u00e4r",
            "attributes": {"nested": {"depth": 2, "list": [1, 2, 3]}, "empty": []},
        },
        {
            "entity_id": "22222222-2222-2222-2222-222222222222",
            "entity_type": "domain",
            "canonical_value": "example.com",
            "attributes": {},
        },
    ],
    "edges": [
        {
            "edge_id": "33333333-3333-3333-3333-333333333333",
            "source_entity_id": "11111111-1111-1111-1111-111111111111",
            "target_entity_id": "22222222-2222-2222-2222-222222222222",
            "relationship": "observed_at",
            "confidence": 0.75,
            "attributes": {"note": "round-trip"},
        }
    ],
}

SAMPLE_MANIFEST: dict[str, Any] = {
    "manifest_version": "0.7.0",
    "phase": 14,
    "goal": "storage conformance",
    "seeds": [{"type": "username", "value": "sn\u00f6b\u00e4r"}],
    "completed": [],
    "pending": [],
    "chain_tip": "0" * 64,
}


class _Recorder:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.failed = False

    def check(self, name: str, fn) -> None:
        """Run ``fn``; record pass/fail. Skipped once a check has failed."""
        if self.failed:
            self.checks.append({"name": name, "ok": False, "skipped": True, "detail": "prior check failed"})
            return
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001 - conformance reports, never masks
            self.failed = True
            self.checks.append(
                {"name": name, "ok": False, "skipped": False, "detail": f"{type(exc).__name__}: {exc}"}
            )
            return
        self.checks.append({"name": name, "ok": True, "skipped": False, "detail": detail or ""})


def conform(backend: StorageBackend) -> dict[str, Any]:
    """Exercise the full storage-backend contract and return a result record."""
    rec = _Recorder()
    run_id = str(uuid4())
    other_run_id = str(uuid4())

    rec.check("health", lambda: backend.health().get("backend"))
    rec.check("migrate", lambda: _migrate(backend))
    rec.check("migrate_idempotent", lambda: _migrate_again(backend))
    rec.check("load_missing_graph_is_none", lambda: _expect_none(backend.load_graph(other_run_id)))
    rec.check("load_missing_manifest_is_none", lambda: _expect_none(backend.load_manifest(other_run_id)))
    rec.check("save_graph", lambda: backend.save_graph(run_id, SAMPLE_GRAPH))
    rec.check("graph_round_trip", lambda: _expect_equal(backend.load_graph(run_id), SAMPLE_GRAPH))
    rec.check(
        "graph_materialised",
        lambda: _materialised(backend, run_id, len(SAMPLE_GRAPH["entities"]), len(SAMPLE_GRAPH["edges"])),
    )
    rec.check("graph_overwrite", lambda: _overwrite(backend, run_id))
    rec.check(
        "overwrite_materialised",
        lambda: _materialised(backend, run_id, 0, 0),
    )
    rec.check("save_manifest", lambda: backend.save_manifest(run_id, SAMPLE_MANIFEST))
    rec.check("manifest_round_trip", lambda: _expect_equal(backend.load_manifest(run_id), SAMPLE_MANIFEST))
    rec.check("list_runs_contains_run", lambda: _contains(backend.list_runs(), run_id))
    rec.check("list_runs_sorted", lambda: _sorted(backend.list_runs()))

    return {
        "backend": backend.backend_name,
        "ok": not rec.failed,
        "run_id": run_id,
        "checks": rec.checks,
    }


def _migrate(backend: StorageBackend) -> str:
    result = MigrationRunner(backend).run()
    pending_after = MigrationRunner(backend).status()["pending"]
    if pending_after:
        raise AssertionError(f"migrations still pending after run: {pending_after}")
    return f"applied_now={result['applied_now']}"


def _migrate_again(backend: StorageBackend) -> str:
    result = MigrationRunner(backend).run()
    if result["applied_now"]:
        raise AssertionError(f"second run re-applied migrations: {result['applied_now']}")
    return "no-op"


def _expect_none(value: Any) -> str:
    if value is not None:
        raise AssertionError(f"expected None, got {value!r}")
    return "None"


def _expect_equal(actual: Any, expected: Any) -> str:
    if actual != expected:
        raise AssertionError(f"round-trip mismatch: {actual!r} != {expected!r}")
    return "exact"


def _overwrite(backend: StorageBackend, run_id: str) -> str:
    replacement = {"entities": [], "edges": [], "note": "replaced"}
    backend.save_graph(run_id, replacement)
    return _expect_equal(backend.load_graph(run_id), replacement)


def _contains(values: list[str], wanted: str) -> str:
    if wanted not in values:
        raise AssertionError(f"{wanted} not in {values}")
    return f"{len(values)} run(s)"


def _sorted(values: list[str]) -> str:
    if values != sorted(values):
        raise AssertionError(f"list_runs not sorted: {values}")
    return "sorted"


def _materialised(backend: StorageBackend, run_id: str, entities: int, edges: int) -> str:
    """Optional backend-specific check; backends without one pass trivially.

    The hook's return value is validated against the expected counts, so a
    backend that materialises the wrong number of nodes or relationships fails
    even if it reports success.
    """
    hook = getattr(backend, "verify_materialised", None)
    if hook is None:
        return "n/a"
    observed = hook(run_id, entities, edges)
    counts = {"entities": observed.get("entities"), "edges": observed.get("edges")}
    if counts != {"entities": entities, "edges": edges}:
        raise AssertionError(f"materialised counts {counts} != expected entities={entities} edges={edges}")
    return f"entities={counts['entities']} edges={counts['edges']}"
