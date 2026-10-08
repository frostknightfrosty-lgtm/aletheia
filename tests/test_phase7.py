import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from aletheia.api.app import app, benchmarks
from aletheia.mcp.server import MCPServer
from aletheia.phase7.benchmark import BenchmarkStore


def test_benchmark_metrics_are_label_derived(tmp_path):
    store = BenchmarkStore(tmp_path / "bench.sqlite3")
    store.record(adapter="demo", seed_type="name", seed_value="Acme", expected=["a", "b"], observed=["a", "c"], duration_ms=50, negative_count=8)
    row = store.leaderboard()[0]
    assert row["adapter"] == "demo"
    assert row["precision"] == 0.5
    assert row["recall"] == 0.5
    assert row["coverage"] == 0.5
    assert row["false_positive_rate"] == 1/9
    assert row["avg_duration_ms"] == 50.0


def test_benchmark_api_accepts_case(tmp_path, monkeypatch):
    local = BenchmarkStore(tmp_path / "bench.sqlite3")
    monkeypatch.setattr("aletheia.api.app.benchmarks", local)
    client = TestClient(app)
    response = client.post("/v1/benchmarks/cases", json={
        "adapter": "demo", "seed_type": "name", "seed_value": "Acme",
        "expected": ["x"], "observed": ["x", "y"], "duration_ms": 12.0,
    })
    assert response.status_code == 200
    assert response.json()["case_id"]
    assert local.leaderboard()[0]["precision"] == 0.5


def test_ui_root_is_self_contained():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Aletheia" in r.text
    assert "renderGraph" in r.text


def test_mcp_tools_and_manifest(tmp_path):
    server = MCPServer(tmp_path)
    tools = server.tools()
    names = {t["name"] for t in tools}
    assert {"investigate", "resume", "manifest", "graph", "benchmark_leaderboard"} <= names


def test_mcp_initialize_round_trip(tmp_path, monkeypatch, capsys):
    # Exercise the server framing with one initialize request.
    import io, sys
    from aletheia.mcp import server as mod
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}\n'))
    mod.serve(tmp_path)
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["id"] == 1
    assert payload["result"]["serverInfo"]["name"] == "aletheia"
    assert payload["result"]["capabilities"]["tools"] == {}


def test_execution_telemetry_can_exist_without_labels(tmp_path):
    store = BenchmarkStore(tmp_path / "bench.sqlite3")
    store.record_execution(adapter="demo", duration_ms=123.0, status="succeeded")
    row = store.leaderboard()[0]
    assert row["adapter"] == "demo"
    assert row["execution_samples"] == 1
    assert row["avg_duration_ms"] == 123.0
    assert row["label_quality"] == "unlabeled"
    assert row["precision"] is None and row["recall"] is None
