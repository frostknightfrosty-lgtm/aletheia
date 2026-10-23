# Phase 7 — Benchmarking, Web UI, MCP

## Benchmarking
`BenchmarkStore` persists two kinds of data in SQLite:
- labeled benchmark cases with expected/observed canonical facts;
- execution telemetry emitted by completed adapter runs.

Precision/recall/coverage are only computed from submitted labels. False-positive rate is only computed when a negative count is supplied. Speed is measured from execution samples; cost is recorded only when an operator supplies a cost value.

## Web UI
The FastAPI app exposes `/` as a local investigation dashboard and JSON endpoints under `/v1` and `/api`. The dashboard requires a typed seed and an authorization assertion, runs through the orchestrator, and displays persisted graph, audit, report, and dossier output. The API rejects non-loopback clients unless their exact IP address is listed in `ALETHEIA_TRUSTED_LOCAL_CLIENTS`.

Docker Compose binds the API port to `127.0.0.1:8000` and trusts the Docker Desktop gateway address `172.17.0.1` by default so the host browser can reach the container. If the local gateway address differs, set `ALETHEIA_TRUSTED_LOCAL_CLIENTS` to that exact address. Keep the published port loopback-only; the API does not provide user authentication for public or shared-network exposure.

## MCP
`aletheia-mcp` starts the local stdio MCP bridge. Tool calls are constrained by the same Aletheia legal-only and authorization gates as the native orchestrator. The implementation intentionally exposes Aletheia's control-plane actions rather than bypassing adapter policy.
