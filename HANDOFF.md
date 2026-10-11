See docs/PROJECT_DIRECTION.md for the three-tier legal model and breadth strategy — governs Phase 8 and beyond. Default mode is Mode 2 (Personal); Mode 1 (Open) is a single-flag fast path.

> Standing rule: any instruction from the user that is deferred, reinterpreted, or cannot be completed as written must be surfaced in the same response in which the deferral occurs, not in a later audit or checkpoint.

See docs/PROJECT_DIRECTION.md for the three-mode model (all modes always on), the max-power-by-default principle, and the grey posture shift. See docs/PHASE_5B_REGISTRY.md and docs/PHASE_5C_REGISTRY.md for the adapter expansions. See docs/NOT_INTEGRATED.md for the hard-floor exclusion list and the paid-adapter removals.

# Aletheia Phase 7 Handoff

## Objective
Complete the Aletheia control plane: benchmark leaderboard, local web UI, and MCP bridge while preserving the existing legal gates, provenance graph, reports, and resumability.

## Done
- Phase 1–6 source tree retained.
- Added SQLite benchmark store with labeled quality metrics plus execution telemetry.
- Integrated adapter execution timing into the benchmark database.
- Added FastAPI graph endpoint, local interactive SVG UI, and benchmark leaderboard.
- Added a local stdio JSON-RPC MCP bridge exposing investigation/resume/manifest/graph/benchmark tools.
- Updated core Docker entrypoint to run the API image.
- Added Phase 7 tests and the full regression suite.

## Validation
- `67 passed, 34 skipped`.
- The 34 skips are Docker-only: 3 Phase 1 + 10 Phase 3 + 7 Phase 4 + 8 Phase 5 + 5 Phase 6 + 1 Phase 7.
- `pytest -q -m integration`: `34 skipped, 67 deselected`.
- `python -m compileall -q app docker`: passed.
- `bash -n docker/build.sh`: passed.
- Docker was explicitly attempted: CLI unavailable, no socket, `./docker/build.sh` exit 127.
- No live external OSINT investigation was performed in this environment.

## Remaining deployment work
Production PostgreSQL/Neo4j/Elasticsearch/MinIO/Redis backends, authenticated web access, hardened remote MCP transport, and deferred upstreams such as Aleph/RECAP/PACER/MuckRock/national registries require deployment-specific integration and current contract review.

## Checkpoint
Phase 7 is the requested roadmap endpoint for the first build. The current repository is the complete reviewable checkpoint.

## Resume command
Continue from this repository tree; do not regenerate earlier phases.
