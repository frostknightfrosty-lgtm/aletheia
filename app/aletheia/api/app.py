from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, model_validator

from aletheia.core.models import ContextFilters, Seed
from aletheia.core.orchestrator import Orchestrator
from aletheia.phase2.service import Phase2Service
from aletheia.phase7.benchmark import BenchmarkStore
from aletheia.phase7.ui import page

class InvestigationStartRequest(BaseModel):
    seed: Seed | None = None
    seeds: list[Seed] | None = None
    authorization_assertion: str | None = None
    context_filters: ContextFilters | None = None

    @model_validator(mode="after")
    def _require_seeds(self) -> "InvestigationStartRequest":
        if self.seed is None and not self.seeds:
            raise ValueError("provide seed or seeds")
        return self


app = FastAPI(title="Aletheia", version="0.7.0")
DATA_DIR = Path(os.getenv("ALETHEIA_DATA_DIR", "./data"))
orch = Orchestrator(DATA_DIR)
phase2 = Phase2Service(DATA_DIR)
benchmarks = BenchmarkStore(DATA_DIR / "benchmarks.sqlite3")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "phase": "7"}


@app.post("/v1/investigations")
def start_investigation(request: InvestigationStartRequest) -> dict[str, str]:
    run_id = orch.create_run(
        request.seeds or request.seed,
        legal_only=True,
        authorization_assertion=request.authorization_assertion,
        context_filters=request.context_filters,
    )
    return {"run_id": str(run_id), "status": "created"}


@app.post("/v1/investigations/{run_id}/phase2")
def finalize_phase2(run_id: UUID) -> dict:
    try:
        return phase2.finalize(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.get("/v1/investigations/{run_id}")
def investigation(run_id: UUID) -> dict:
    manifest = orch.checkpoints.load(run_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="run not found")
    return manifest


@app.get("/", response_class=HTMLResponse)
def ui_root():
    return page()

@app.get("/v1/investigations/{run_id}/graph")
def investigation_graph(run_id: UUID) -> dict:
    path = orch.graph_store.root / str(run_id) / "graph.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="graph not found")
    import json
    return json.loads(path.read_text(encoding="utf-8"))

@app.get("/v1/benchmarks/leaderboard")
def benchmark_leaderboard() -> dict:
    return {"rows": benchmarks.leaderboard()}

class BenchmarkRecordRequest(BaseModel):
    adapter: str
    seed_type: str
    seed_value: str
    expected: list[str] = []
    observed: list[str] = []
    duration_ms: float
    negative_count: int | None = None
    cost: float | None = None

@app.post("/v1/benchmarks/cases")
def benchmark_case(request: BenchmarkRecordRequest) -> dict[str, str]:
    case_id = benchmarks.record(
        adapter=request.adapter, seed_type=request.seed_type, seed_value=request.seed_value,
        expected=request.expected, observed=request.observed, duration_ms=request.duration_ms,
        negative_count=request.negative_count, cost=request.cost,
    )
    return {"case_id": case_id}
