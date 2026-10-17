# Aletheia Handoff — Phase 13 complete (score calibration)

Last updated: 2026-10-17T15:10:00Z

## Project boundaries

Aletheia is a free, open-source OSINT investigation platform under the Florida project
policy (`docs/DIRECTIVE_AMENDMENT_FLORIDA.md`). Sources sit on five tiers; the only project
gate is the Tier 5 hard floor: unauthorized computer access (including another person's
credentials or CAPTCHA/paywall bypass), communications interception, criminal marketplace
transactions, and stalking/harassment. Tier 1–4 sources run by default when their
prerequisites are met. A tier classification is project policy, not a legal conclusion.

## Repository and CI state

- Latest CI-verified commit: `f1a9a840c3dc9e0e16caefb640b2c934b2b6edeb`
  (`phase-13: implement score calibration (Platt + isotonic)`).
- Docker Verification run **38972618582** —
  https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38972618582 — **green**.
- Evidence lines copied from the downloaded artifact
  (`ci-artifacts-38972618582`), not typed:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - `634 passed, 1 warning in 30.13s`
  - `DOCKER CAPTURE: PASS — 55/55 cases captured`
- `results.json`: 55 entries, 0 nonzero return codes.
- Local consistency: **580 passed + 54 skipped = 634**, which equals the CI passed count
  exactly. The state-only commit `9bdf8cf` (`state: record Phase 12 proxy wiring, next is
  score calibration`) also passed run `38972568001` (`616 passed`; capture 55/55).
- 49 registered adapters, all `verified-fixture`. No `verified-live` adapters. One
  infrastructure component (`egress_proxy`), `verified-fixture`.

## Phase 13 — score calibration (complete)

Implemented and CI-verified in commit `f1a9a84`.

- `app/aletheia/core/calibration.py` — new. `PlattScaling` fits `sigmoid(slope * score +
  intercept)` by Newton-Raphson on Platt-smoothed targets; `IsotonicRegression` fits a
  monotone step function by pool-adjacent-violators. Both are pure standard library (the
  project installs no numeric package). `Calibrator` wraps them and keeps `trained` `False`
  below `MIN_LABELED_PAIRS = 8` pairs or when a class is missing, so an untrained model is
  never presented as a probability. Dict round-trip via `to_dict`/`from_dict`.
- `app/aletheia/phase2/resolution.py` — `EntityResolver` takes an optional `Calibrator` and
  reports `calibrated` / `calibrated_probability` per `SAME_AS_CANDIDATE` edge
  (`attributes.resolution`). Without a trained calibrator these are `false` / `null` and the
  raw Jaro-Winkler/Levenshtein composite is retained as a similarity score.
- `tests/test_calibration.py` — 18 tests (monotonicity, boundedness, degenerate input,
  serialization round-trip, untrained-honesty, resolver integration).
- `tests/fixtures/calibration_pairs.json` — 80 **synthetic** labelled pairs, deterministically
  generated (seed 20261017). This is not real investigation data.
- `docs/ADAPTER_CONTRACT.md` — new "Calibrated vs uncalibrated scores" section.
- Honest limitation: the fixture is synthetic, so the fitted probabilities demonstrate the
  mechanism only; real calibration is deferred until labelled pairs from authorised
  investigations exist. The `calibrated` flag and the component contract are the stable part.

## Phase 12 — egress proxy wiring (complete)

Implemented and CI-verified in commit `ccd5a4b`.

- `app/aletheia/core/egress.py` — added `ProxySession` (creates an `--internal` Docker
  network and starts the detached proxy on it, no published host port), `create_network_command`,
  `remove_network_command`, `network_name`, `EGRESS_WIRED_ADAPTERS`, `is_wired`, and a
  DNS-safe container name (underscores become hyphens, because DNS labels cannot carry them).
  `EgressProxy.run_command` gained `detached` and `publish_port`.
- `app/aletheia/core/execution.py` — `run_docker(..., network_name=...)` joins a named
  network (the internal one), overriding the old `bridge`/`none` choice.
- `app/aletheia/core/models.py` / `core/adapters.py` — `AdapterRunRequest.network_name`
  is threaded through to `run_docker`.
- `app/aletheia/core/orchestrator.py` — `resume(..., wire_egress=True)` starts a
  `ProxySession` for each *wired* adapter, sets `proxy_url`/`network_name`, and appends the
  proxy's request log to the run's Phase 10 chain as `egress_request` events.
- Wired subset (3 of 49): `search_engines`, `ssl_tls`, `ip_intelligence`. The other 46 keep
  their previous behaviour; full coverage is deferred.
- `ci/egress_scenario.py` — new. Runs the whole shape on a real `--internal` network (a local
  origin plus the adapter image as the client) and asserts: the forwarded request returns 200
  and is logged; the real `search_engines` runner egresses through the proxy (`rc=0`); four
  `egress_request` events append to a chain that verifies valid; and the fail-closed property
  (no direct internet; no path once the proxy is stopped).
- `tests/test_egress_wiring.py` — 11 unit tests (argv builders, `ProxySession` with an
  injected runner, `run_docker` network selection, orchestrator wiring gating).
- `tests/test_docker_integration.py` — 3 new integration tests sharing one scenario run.
- `ci/capture_docker_integration.py` — records the 4 `phase12-egress-*` scenario checks.
- `docs/EGRESS_PROXY_CONTRACT.md` — new "Wiring pattern" section; status updated.
- Honest limitation: the proxy is wired into three adapters, not all 49. The scenario proves
  the pattern with the adapter image as the client and the real `search_engines` runner; per
  the standing rules it uses no live internet (the network is `--internal`).

## Phase 10 — hash-chained audit log (complete)

Implemented and CI-verified in commit `5037108`.

- `app/aletheia/core/chain.py` — new. A SHA-256 hash chain over each run's `AUDIT.jsonl`.
  Every entry carries `seq` (1-based), `prev_hash` (the previous entry's hash, or 64 zeroes
  for the genesis entry) and `hash` (SHA-256 of the canonical UTF-8 JSON with `hash`
  removed, keys sorted, compact separators). `append()` refuses to extend an invalid chain
  or a chain whose tip disagrees with the run `MANIFEST.json` anchor. `verify()` checks
  entry order, previous-hash links, entry hashes, the manifest `checkpoint_hash`, and the
  manifest `chain_tip` anchor.
- `app/aletheia/core/audit.py` — every `AuditLogger.log()` now appends through the chain.
- `app/aletheia/core/orchestrator.py` — publishes the verified `chain_tip` into the manifest
  on resume; a broken chain raises instead of being silently rewritten.
- `app/aletheia/core/checkpoint.py` — unchanged; the manifest already persists arbitrary
  keys, so `chain_tip` rides on the existing `CheckpointStore.save()` with its
  `checkpoint_hash`.
- `app/aletheia/phase2/service.py` — verifies the chain before any Phase 2 mutation.
- `app/aletheia/cli/main.py` — new `aletheia verify-chain <RUN_ID> [--data-dir …]` command.
- Tests: `tests/test_chain.py` (10 tests) plus `tests/test_phase2_service.py` chain-tip
  assertion. Tamper detection is covered (edited entry, removed final entry, stale
  manifest anchor, tampered checkpoint hash).

### Honest limitation (recorded, not softened)

The chain is **tamper-evident relative to a preserved manifest anchor**. It is **not** a
digital signature, it does not authenticate the manifest against an actor who can rewrite
both files together, and it is **not** a legal-admissibility guarantee. The README and
`docs/ADAPTER_CONTRACT.md` say the same thing.

## Phase 11 — egress proxy, standalone component (complete)

Implemented and CI-verified in commit `02ee887`; manifest status flipped in `255dc6d`.

- `app/aletheia/core/egress.py` — new control-plane module. `EgressLogEntry` /
  `parse_log_line` / `read_log` validate the proxy's JSONL schema; `TokenBucket` and
  `AdapterRateLimiter` implement a per-adapter token bucket with optional JSON persistence
  (atomic temp-file replace + `fsync`); `KillSwitch` reads an env flag or a flag file;
  `EgressProxy` builds the `docker run` argv and the `HTTP_PROXY`/`HTTPS_PROXY` environment
  for an adapter; `append_log_to_chain` writes each proxied request to the run's hash chain
  (`chain.append`, so a tampered run refuses the append).
- `docker/egress_proxy/proxy.py` — new. A standard-library `asyncio` forward proxy. Plain
  HTTP is forwarded from an absolute-form target; HTTPS `CONNECT` is tunnelled. The kill
  switch (403) and the token bucket (429) are applied before any upstream connection is
  opened; an upstream connect failure logs 502. `--health` prints exactly `ok` and opens no
  socket, so the container smoke runs under `--network none`. **Deviation, recorded:** the
  module is not literally ASGI — ASGI cannot carry `CONNECT` tunnels — so the forwarder is a
  stdlib `asyncio` server; the control-plane contract in `docs/EGRESS_PROXY_CONTRACT.md`
  is unchanged.
- `docker/egress_proxy/Dockerfile` — image `aletheia/egress-proxy:v1`, stdlib only, non-root
  `aletheia` user, no third-party package.
- `tests/test_egress.py` (31 tests) plus `tests/fixtures/egress_proxy_log.jsonl`; a
  container-health smoke in `tests/test_docker_integration.py`; capture case
  `phase11-egress-proxy` in `ci/capture_docker_integration.py`; a `docker/build.sh` target;
  a `PROJECT_MANIFEST.json` entry as an infrastructure component with `enabled_by_default:
  true` (invocation deliberately omits the substring `Docker` so the adapter set stays 49).
- `docs/EGRESS_PROXY_CONTRACT.md` — created (it was missing). It is the design/contract
  record for the component.

### Honest limitation (recorded, not softened)

The proxy log records what reached the proxy; it is **not** proof of what an adapter did
before that point, and the chain it feeds is **tamper-evident relative to a preserved run
manifest**, not a digital signature and not a legal-admissibility guarantee.

## Next action

**Phase 12 — not started.** The egress proxy is a standalone component only; it is **not**
yet wired into the adapter Dockerfiles, so no adapter traffic is forced through it and there
is no per-request proxy logging, rate limiting, kill switch, or network-level fail-closed
behaviour in the running system. Wiring the proxy into the adapter images and the run
network is the next session. The `docs/EGRESS_PROXY_CONTRACT.md` design record exists.

## Known deferred issues

- No adapter traffic is yet forced through an egress proxy; the Phase 11 component
  (`app/aletheia/core/egress.py`, `docker/egress_proxy`) exists and is CI-verified, but it is
  not wired into the adapter Dockerfiles or the run network, so there is no per-request proxy
  logging, rate limiting, kill switch, or network-level fail-closed behaviour in the running
  system yet.
- Graph/checkpoint storage is file-backed JSON; no Postgres/Neo4j/Elasticsearch/MinIO/Redis
  backends yet.
- No `verified-live` adapters; every fixture is synthetic unless separately documented.
- Score/confidence separation is incomplete; `--purpose` is not a required adapter field.
- `AUTONOMOUS_DIRECTIVE.md` and `AGENT_SETUP.md` live at the repo root, but both reference
  `docs/AUTONOMOUS_DIRECTIVE.md`. Worth fixing or documenting.
- The audit trail of unverified claims in `RESUME_STATE.json` before 2026-10-14 should be
  treated as reconstructed, not primary evidence.

## Open gates

- **Gate 2** — user-owned target required before any live investigation.
- **Gate 3** — verify API keys and cost before a phase depends on them.
- **Gate 5** — evidence lines must be copied from a downloaded artifact, never typed.
- **Gate 6** — `transport_movement` and `darkweb_search` remain deferred pending user
  action / source verification.

## Briefing corrections (standing rule 10)

- The session brief said Phase 10 was uncommitted, left one failing test double, and that
  the local suite was 518 passed / 50 skipped (568 total). All three were stale: Phase 10
  was already committed as `5037108` and pushed; the test double in `tests/test_chain.py`
  already creates the per-adapter workspace (matching `Adapter.run`); and the real local
  count is 520 passed / 50 skipped = 570, matching CI.
