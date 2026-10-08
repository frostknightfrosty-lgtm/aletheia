# Phase 7 — Benchmarking, Web UI, MCP

## Benchmarking
`BenchmarkStore` persists two kinds of data in SQLite:
- labeled benchmark cases with expected/observed canonical facts;
- execution telemetry emitted by completed adapter runs.

Precision/recall/coverage are only computed from submitted labels. False-positive rate is only computed when a negative count is supplied. Speed is measured from execution samples; cost is recorded only when an operator supplies a cost value.

## Web UI
The FastAPI app exposes `/` as a local single-page graph/leaderboard view and JSON endpoints under `/v1`. It is deliberately unauthenticated in this development checkpoint and should not be exposed publicly without an authentication/authorization layer.

## MCP
`aletheia-mcp` starts the local stdio MCP bridge. Tool calls are constrained by the same Aletheia legal-only and authorization gates as the native orchestrator. The implementation intentionally exposes Aletheia's control-plane actions rather than bypassing adapter policy.
