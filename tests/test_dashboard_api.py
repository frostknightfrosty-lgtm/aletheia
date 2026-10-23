from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

import aletheia.api.app as api


def test_api_rejects_nonlocal_clients_but_allows_explicit_docker_gateway(monkeypatch) -> None:
    monkeypatch.setattr(api, "TRUSTED_LOCAL_CLIENTS", frozenset())
    remote = TestClient(api.app, client=("203.0.113.5", 43120))
    assert remote.get("/").status_code == 403
    assert remote.get("/healthz").status_code == 200

    monkeypatch.setattr(
        api,
        "TRUSTED_LOCAL_CLIENTS",
        frozenset({ipaddress.ip_address("172.17.0.1")}),
    )
    docker_host = TestClient(api.app, client=("172.17.0.1", 43120))
    response = docker_host.get("/")
    assert response.status_code == 200
    assert "renderGraph" in response.text


def test_dashboard_starts_typed_seed_and_queues_real_run(monkeypatch) -> None:
    run_id = uuid4()
    created: dict[str, object] = {}
    queued: list[tuple[object, object]] = []

    def fake_create_run(seed, **kwargs):
        created["seed"] = seed
        created.update(kwargs)
        return run_id

    monkeypatch.setattr(api.orch, "create_run", fake_create_run)
    monkeypatch.setattr(
        api,
        "_execute_dashboard_run",
        lambda identifier, request: queued.append((identifier, request)),
    )
    response = TestClient(api.app).post(
        "/api/investigate",
        json={
            "seed": {"type": "username", "value": "throwaway_user"},
            "authorization_assertion": "  I own this test account.  ",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"run_id": str(run_id), "status": "queued"}
    assert created["seed"].value == "throwaway_user"
    assert created["legal_only"] is True
    assert created["authorization_assertion"] == "I own this test account."
    assert queued[0][0] == run_id


def test_dashboard_requires_nonblank_authorization_assertion(monkeypatch) -> None:
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("invalid request must not create a run")

    monkeypatch.setattr(api.orch, "create_run", fail_if_called)
    response = TestClient(api.app).post(
        "/api/investigate",
        json={
            "seed": {"type": "username", "value": "throwaway_user"},
            "authorization_assertion": "   ",
        },
    )

    assert response.status_code == 422
    assert called is False


def test_dashboard_serves_run_status_graph_and_dossier_as_text(tmp_path: Path, monkeypatch) -> None:
    run_id = uuid4()
    graph_root = tmp_path / "graphs"
    run_dir = tmp_path / "runs" / str(run_id)
    graph_dir = graph_root / str(run_id)
    graph_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    (graph_dir / "graph.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "entity_id": "entity-1",
                        "canonical_value": "throwaway_user",
                        "entity_type": "username",
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "AUDIT.jsonl").write_text('{"event_type":"started"}\n', encoding="utf-8")
    (run_dir / "dossier.md").write_text("# Dossier\n<script>literal text</script>\n", encoding="utf-8")

    fake_orch = SimpleNamespace(
        checkpoints=SimpleNamespace(load=lambda identifier: {"pending": [], "reports": {"json": "ready"}}),
        graph_store=SimpleNamespace(root=graph_root),
    )
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api, "orch", fake_orch)
    client = TestClient(api.app)

    status = client.get(f"/api/run/{run_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "complete"
    assert '"event_type":"started"' in status.json()["audit_tail"]

    graph = client.get(f"/api/run/{run_id}/graph")
    assert graph.status_code == 200
    assert graph.json()["nodes"][0]["data"]["label"] == "throwaway_user"

    dossier = client.get(f"/api/run/{run_id}/dossier")
    assert dossier.status_code == 200
    assert dossier.headers["content-type"].startswith("text/plain")
    assert "<script>literal text</script>" in dossier.text
