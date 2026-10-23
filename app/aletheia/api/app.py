from __future__ import annotations

import ipaddress
import json
import os
from collections import deque
from pathlib import Path
from threading import Lock
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from aletheia.core.models import ContextFilters, Seed
from aletheia.core.orchestrator import Orchestrator
from aletheia.phase2.service import Phase2Service
from aletheia.phase7.benchmark import BenchmarkStore
from aletheia.reporting.dossier import generate_dossier


API_DIR = Path(__file__).resolve().parent
STATIC_DIR = API_DIR / "static"
INDEX_PATH = API_DIR / "templates" / "index.html"
DATA_DIR = Path(os.getenv("ALETHEIA_DATA_DIR", "./data")).expanduser().resolve()
AUDIT_TAIL_LINES = 100
TRUSTED_LOCAL_CLIENTS = frozenset(
    ipaddress.ip_address(value.strip())
    for value in os.getenv("ALETHEIA_TRUSTED_LOCAL_CLIENTS", "").split(",")
    if value.strip()
)


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


class DashboardInvestigationRequest(BaseModel):
    seed: Seed
    authorization_assertion: str = Field(min_length=1, max_length=2048)
    timeout_seconds: int = Field(default=120, ge=1, le=1800)

    @field_validator("authorization_assertion")
    @classmethod
    def _assertion_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("authorization_assertion must not be blank")
        return value


class BenchmarkRecordRequest(BaseModel):
    adapter: str
    seed_type: str
    seed_value: str
    expected: list[str] = Field(default_factory=list)
    observed: list[str] = Field(default_factory=list)
    duration_ms: float
    negative_count: int | None = None
    cost: float | None = None


app = FastAPI(title="Aletheia", version="0.7.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
orch = Orchestrator(DATA_DIR)
phase2 = Phase2Service(DATA_DIR)
benchmarks = BenchmarkStore(DATA_DIR / "benchmarks.sqlite3")

_dashboard_runs: dict[str, dict[str, str]] = {}
_dashboard_runs_lock = Lock()


@app.middleware("http")
async def local_only_api(request: Request, call_next):
    """Keep the unauthenticated operator API bound to local clients by default."""
    if request.url.path != "/healthz" and not request.url.path.startswith("/static/"):
        host = request.client.host if request.client else ""
        is_local = host == "testclient"
        try:
            address = ipaddress.ip_address(host)
            is_local = is_local or address.is_loopback
            is_local = is_local or address in TRUSTED_LOCAL_CLIENTS
            if getattr(address, "ipv4_mapped", None) is not None:
                is_local = is_local or address.ipv4_mapped.is_loopback
                is_local = is_local or address.ipv4_mapped in TRUSTED_LOCAL_CLIENTS
        except ValueError:
            pass
        if not is_local:
            return JSONResponse(
                status_code=403,
                content={"detail": "The unauthenticated Aletheia API accepts local connections only."},
            )
    return await call_next(request)


def _run_directory(run_id: UUID) -> Path:
    return DATA_DIR / "runs" / str(run_id)


def _record_dashboard_state(run_id: UUID, **fields: str) -> None:
    with _dashboard_runs_lock:
        previous = _dashboard_runs.setdefault(str(run_id), {})
        previous.update(fields)


def _execute_dashboard_run(run_id: UUID, request: DashboardInvestigationRequest) -> None:
    _record_dashboard_state(run_id, status="running", message="Running adapters")
    try:
        # Orchestrator.resume wires network-required containers through the
        # egress proxy by default. Do not disable that safety boundary here.
        orch.resume(
            run_id,
            authorization_assertion=request.authorization_assertion,
            timeout_seconds=request.timeout_seconds,
        )
        _record_dashboard_state(run_id, status="finalizing", message="Generating reports")
        phase2.finalize(run_id)
    except Exception as exc:  # surface the failure to the local dashboard
        _record_dashboard_state(
            run_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}"[:1000],
        )
        return

    _record_dashboard_state(run_id, status="dossier", message="Generating dossier")
    try:
        generate_dossier(str(run_id), str(DATA_DIR), echo=False)
    except Exception as exc:  # reports are already complete; dossier is optional
        _record_dashboard_state(
            run_id,
            status="complete",
            dossier_error=f"{type(exc).__name__}: {exc}"[:1000],
        )
    else:
        _record_dashboard_state(run_id, status="complete")


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


@app.get("/")
def ui_root() -> HTMLResponse:
    try:
        page = INDEX_PATH.read_text(encoding="utf-8")
        styles = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        script = (STATIC_DIR / "main.js").read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Dashboard files are missing") from exc
    page = page.replace("<!-- INLINE_STYLES -->", f"<style>\n{styles}\n</style>")
    page = page.replace("<!-- INLINE_SCRIPT -->", f"<script>\n{script}\n</script>")
    return HTMLResponse(page)


@app.post("/api/investigate")
def dashboard_investigation(
    request: DashboardInvestigationRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    run_id = orch.create_run(
        request.seed,
        legal_only=True,
        authorization_assertion=request.authorization_assertion,
    )
    _record_dashboard_state(run_id, status="queued", message="Queued")
    background_tasks.add_task(_execute_dashboard_run, run_id, request)
    return {"run_id": str(run_id), "status": "queued"}


@app.get("/api/run/{run_id}/status")
def dashboard_run_status(run_id: UUID) -> dict[str, str | None]:
    manifest = orch.checkpoints.load(run_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="run not found")

    with _dashboard_runs_lock:
        state = dict(_dashboard_runs.get(str(run_id), {}))
    if not state:
        if manifest.get("failed"):
            state = {"status": "failed", "error": "An adapter failed; see the run handoff and audit log."}
        elif manifest.get("pending"):
            state = {"status": "running", "message": "Running adapters"}
        elif manifest.get("reports"):
            state = {"status": "complete"}
        else:
            state = {"status": "finalizing", "message": "Finalizing run"}

    audit_path = _run_directory(run_id) / "AUDIT.jsonl"
    try:
        with audit_path.open("r", encoding="utf-8", errors="replace") as stream:
            audit_tail = "".join(deque(stream, maxlen=AUDIT_TAIL_LINES))
    except OSError:
        audit_tail = ""

    return {
        "run_id": str(run_id),
        "status": state.get("status", "unknown"),
        "message": state.get("message"),
        "error": state.get("error"),
        "dossier_error": state.get("dossier_error"),
        "audit_tail": audit_tail,
    }


@app.get("/api/run/{run_id}/graph")
def dashboard_run_graph(run_id: UUID) -> dict[str, list[dict]]:
    graph_path = orch.graph_store.root / str(run_id) / "graph.json"
    if not graph_path.is_file():
        raise HTTPException(status_code=404, detail="graph not found")
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="graph data is unreadable") from exc

    nodes = [
        {
            "data": {
                "id": str(entity.get("entity_id", "")),
                "label": str(entity.get("canonical_value", "")),
                "type": str(entity.get("entity_type", "unknown")),
            }
        }
        for entity in graph.get("entities", [])
    ]
    edges = [
        {
            "data": {
                "id": str(edge.get("edge_id", "")),
                "source": str(edge.get("source_entity_id", "")),
                "target": str(edge.get("target_entity_id", "")),
                "label": str(edge.get("relationship", "")),
            }
        }
        for edge in graph.get("edges", [])
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/api/run/{run_id}/dossier", response_class=PlainTextResponse)
def dashboard_run_dossier(run_id: UUID) -> PlainTextResponse:
    dossier_path = _run_directory(run_id) / "dossier.md"
    if not dossier_path.is_file():
        raise HTTPException(status_code=404, detail="Dossier was not generated for this run")
    try:
        return PlainTextResponse(dossier_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Dossier is unreadable") from exc


@app.get("/v1/investigations/{run_id}/graph")
def investigation_graph(run_id: UUID) -> dict:
    path = orch.graph_store.root / str(run_id) / "graph.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="graph not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/v1/benchmarks/leaderboard")
def benchmark_leaderboard() -> dict:
    return {"rows": benchmarks.leaderboard()}


@app.post("/v1/benchmarks/cases")
def benchmark_case(request: BenchmarkRecordRequest) -> dict[str, str]:
    case_id = benchmarks.record(
        adapter=request.adapter,
        seed_type=request.seed_type,
        seed_value=request.seed_value,
        expected=request.expected,
        observed=request.observed,
        duration_ms=request.duration_ms,
        negative_count=request.negative_count,
        cost=request.cost,
    )
    return {"case_id": case_id}
