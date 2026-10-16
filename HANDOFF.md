# Aletheia Handoff — Phase 10 complete (hash-chained audit log), next Phase 11 (egress proxy)

Last updated: 2026-10-16T20:20:00Z

## Project boundaries

Aletheia is a free, open-source OSINT investigation platform under the Florida project
policy (`docs/DIRECTIVE_AMENDMENT_FLORIDA.md`). Sources sit on five tiers; the only project
gate is the Tier 5 hard floor: unauthorized computer access (including another person's
credentials or CAPTCHA/paywall bypass), communications interception, criminal marketplace
transactions, and stalking/harassment. Tier 1–4 sources run by default when their
prerequisites are met. A tier classification is project policy, not a legal conclusion.

## Repository and CI state

- Latest CI-verified commit: `503710890140d573451ba5363a10655f979e2ed4`
  (`phase-10: implement hash-chained audit log`).
- Docker Verification run **38958865080** —
  https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38958865080 — **green**
  (job 13m50s).
- Evidence lines copied from the downloaded artifact
  (`ci-artifacts-38958865080`), not typed:
  - `PARSER PREFLIGHT: PASS — 49/49 adapters have parser coverage`
  - `570 passed, 1 warning in 23.03s`
  - `DOCKER CAPTURE: PASS — 50/50 cases captured`
- `results.json`: 50 entries, 0 nonzero return codes; SHA-256
  `DA17BD0DF2B83FA6C771ED3B76F45EC42BBF271A3E04A5F186CF5FCAF5C03460`.
- Local consistency: **520 passed + 50 skipped = 570**, which equals the CI passed count
  exactly. CI runs the container smokes that skip without a local Docker CLI.
- 49 registered adapters, all `verified-fixture`. No `verified-live` adapters.

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

## Next action

**Phase 11 — egress proxy, standalone component.** Per the session brief: build the proxy
module (`app/aletheia/core/egress.py`), the image (`docker/egress_proxy/Dockerfile`, tag
`aletheia/egress-proxy:v1`), the forwarder (`docker/egress_proxy/proxy.py`), a synthetic
log fixture, `tests/test_egress.py`, a proxy container-health Docker integration case, a
capture case, a `docker/build.sh` target, and a `PROJECT_MANIFEST.json` entry for
`egress_proxy` as an infrastructure component with `enabled_by_default: true`. Do **not**
wire the proxy into every adapter Dockerfile in this session — that is a later session.

**Note:** `docs/EGRESS_PROXY_CONTRACT.md`, which the brief lists as required reading and as
the governing design doc, **does not exist in the repository**. Phase 11 proceeds from the
explicit deliverable list and must create that document as the design/contract record.

## Known deferred issues

- `docs/EGRESS_PROXY_CONTRACT.md` is missing (see above).
- No adapter traffic is yet forced through an egress proxy; no per-request proxy logging,
  rate limiting, kill switch, or fail-closed behaviour exists in the running system.
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
