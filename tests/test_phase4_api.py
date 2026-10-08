from fastapi.testclient import TestClient

from aletheia.api.app import app, orch


def test_health_reports_current_phase():
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok", "phase": "7"}


def test_start_investigation_persists_authorization_assertion(tmp_path, monkeypatch):
    monkeypatch.setattr(orch, "data_root", tmp_path)
    monkeypatch.setattr(orch, "checkpoints", type(orch.checkpoints)(tmp_path / "runs"))
    client = TestClient(app)
    response = client.post("/v1/investigations", json={
        "seed": {"type": "email", "value": "alice@example.com"},
        "authorization_assertion": "authorized test assertion",
    })
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    manifest = orch.checkpoints.load(__import__("uuid").UUID(run_id))
    assert manifest["authorization_assertion"] == "authorized test assertion"
