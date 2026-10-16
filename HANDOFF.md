# Aletheia Handoff — Phase 11 complete (egress proxy, standalone component)

Last updated: 2026-10-17T00:30:00Z

## Project boundaries

Aletheia is a free, open-source OSINT investigation platform under the Florida project
policy (`docs/DIRECTIVE_AMENDMENT_FLORIDA.md`). Sources sit on five tiers; the only project
gate is the Tier 5 hard floor: unauthorized computer access (including another person's
credentials or CAPTCHA/paywall bypass), communications interception, criminal marketplace
transactions, and stalking/harassment. Tier 1–4 sources run by default when their
prerequisites are met. A tier classification is project policy, not a legal conclusion.

## Repository and CI state

- Latest CI-verified commit: `02ee8879330d5195d48f3a7d47b3c0aa28080422`
  (`phase-11: implement egress proxy (standalone component)`).
- Docker Verification run **38961709929** —
  https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38961709929 — **green**
  (attempt 2; attempt 1 was cancelled after the image-build step stalled on a layer pull).
- Evidence lines copied from the downloaded artifact
  (`ci-artifacts-38961709929`), not typed:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - `602 passed, 1 warning in 20.79s`
  - `DOCKER CAPTURE: PASS — 51/51 cases captured`
- `results.json`: 51 entries, 0 nonzero return codes; the `phase11-egress-proxy` case
  (`docker run --rm --network none aletheia/egress-proxy:v1 --health`) returned 0; SHA-256
  `DEED8B3B1C8F62BD77D0B835666672AA5504076211525C161D4EBA9B2C3EA1CF`.
- Egress-proxy image built in CI (`#9 naming to docker.io/aletheia/egress-proxy:v1 done`),
  image id `sha256:f5af6b1f42d9e8cdb5a637bef81534496aa194fe422e18e1187f61ec4ddd12a0`;
  `docker/egress_proxy/Dockerfile` SHA-256
  `eb7ce40f08eee36733d045d726bee8b6532ee4d196c4dccb2e42bc2ac8e761d1` (matches the local file).
- Local consistency: **551 passed + 51 skipped = 602**, which equals the CI passed count
  exactly. CI runs the container smokes that skip without a local Docker CLI.
- 49 registered adapters, all `verified-fixture`. No `verified-live` adapters. One
  infrastructure component (`egress_proxy`), now `verified-fixture`.

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
