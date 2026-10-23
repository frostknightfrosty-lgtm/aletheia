# Aletheia — Phase 7

Aletheia is a provenance-first meta-OSINT orchestration platform. Its core boundary is a typed adapter system with legal policy, checkpoints, audit events, normalized graph data, entity resolution, and provenance-preserving reports.

## Current status

**Phase 19.2 dashboard runtime repair is CI-verified.** Docker Verification run [40037547697](https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/40037547697) tested commit `315516800638ece05b4924aa2a9175559c8ac92a`. Its downloaded artifact reports `PARSER PREFLIGHT: PASS — 63/63 adapters have parser coverage`, `1223 passed in 65.88s`, `DOCKER CAPTURE: PASS — 97/97 cases captured`, and `STORAGE CONFORMANCE: PASS — 6/6 backends conform`. This verifies build, tests, Docker captures, and storage conformance; it does not verify live-source accuracy or mean the full roadmap is complete.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

On a Docker host:

```bash
./docker/build.sh
pytest -q -m integration
```

Personal-identifier and selected network/social/cloud adapters require an explicit authorization assertion:

```bash
aletheia investigate --seed username:alice --legal-only --authorization-assertion "I am authorized to investigate this identifier."
aletheia investigate --seed name:Acme\ Corporation --legal-only --authorization-assertion "I am authorized to investigate this corporate-record lookup."
aletheia investigate --seed email:alice@example.com --legal-only --authorization-assertion "I am authorized to investigate this email."
aletheia investigate --seed geolocation:51.5074,-0.1278 --legal-only --authorization-assertion "I am authorized to investigate this supplied coordinate."
aletheia investigate --seed image:/path/to/photo.jpg --legal-only --authorization-assertion "I am authorized to analyze this image."
```

`libphonenumber` and `SunCalc` remain offline deterministic utilities and do not require the assertion.

## Email breach checks

XposedOrNot is constrained to its free community `check-email` endpoint with the detailed response omitted. The adapter records breach names only; it does not retrieve passwords or breach records. Use it only for an email address you are authorized to investigate, and respect the upstream personal-use limits of 25 requests per hour and 100 per day per IP. Its synthetic, documentation-derived parser fixture and Docker health smoke passed in CI run [38168341113](https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38168341113); no live lookup has been made.

Finalize a completed run with entity resolution and reports:

```bash
aletheia phase2 --run-id <RUN_ID>
```

This writes `report.json`, `report.pdf`, `graph.graphml`, `report.stix2.json`, `resolution.json`, hashes, and an updated `HANDOFF.md` under the run directory.

The report lists every matching adapter with its outcome and the reason for each sub-source it could not query (missing keys, retired endpoints, paid-only APIs), plus informational jurisdiction warnings when a seed or finding indicates a strong-privacy jurisdiction, a minor, health data, or a protected-class context.

## Multi-seed investigations

Repeat `--seed` to expand several seeds in one run. Each seed grows its own evidence tree (`Provenance.seed_index`), resolution runs an intersection pass where entities corroborated by more than one tree get a bounded, documented score boost, and optional context filters flag candidates that positively mismatch a recorded attribute (entities with no comparable attribute are never excluded):

```bash
aletheia investigate --seed domain:example.com --seed email:alice@example.com --filter-country gb
```

Semantics, compatibility, and honest limits are in [`docs/MULTI_SEED.md`](docs/MULTI_SEED.md) and [`docs/JURISDICTION_WARNINGS.md`](docs/JURISDICTION_WARNINGS.md).

## Audit chain

Each run's `AUDIT.jsonl` is a SHA-256 hash chain. Entries carry a sequence number, the previous entry's hash, and their own hash; the final `chain_tip` is stored in that run's `MANIFEST.json`. Verify a run with `aletheia verify-chain <RUN_ID>`. This makes changes detectable relative to the manifest anchor, but it is not a digital signature or a guarantee of legal admissibility; preserve and protect the manifest and audit files together.

## Egress proxy

Adapter traffic goes through a local forward proxy that logs every request (adapter, method, host, path, status, bytes, purpose id, timestamp), enforces a per-adapter rate limit, and provides one kill switch. The proxy runs on a per-adapter `--internal` Docker network, so a container on it has no route out except the proxy; if the proxy is down, the adapter cannot reach the internet.

Coverage is a policy, not an allowlist: every adapter whose descriptor declares `network_required=True` is wired. `aletheia investigate` and `aletheia resume` wire by default; pass `--no-egress-proxy` only for offline replays. The request log is appended to the run's hash-chained `AUDIT.jsonl` as `egress_request` events. See [`docs/EGRESS_PROXY_CONTRACT.md`](docs/EGRESS_PROXY_CONTRACT.md) for the contract and the honest limits (the log records what reached the proxy, and an adapter whose client ignores the proxy variables fails closed rather than egressing unproxied).

## Storage backends (Phase 14)

Graph snapshots and run manifests persist through one backend contract. The default is the local file store; five networked backends implement the same contract: PostgreSQL, Neo4j, Elasticsearch, an S3-compatible object store (`minio`), and Redis (fast-path cache). Drivers live in the `storage` extra (`pip install -e '.[storage]'`).

```bash
aletheia storage health
aletheia storage migrate --backend postgres
aletheia storage sync --run-id <RUN_ID> --backend minio
```

A shared conformance contract runs against every backend, and a migration runner applies each schema migration once and records a checksum so drift is detected. The file store stays authoritative and the hash-chained audit log deliberately remains on local disk. See [`docs/STORAGE_BACKENDS.md`](docs/STORAGE_BACKENDS.md) for configuration, the CI verification path, and the honest limits (including why S3 verification uses an S3-protocol server rather than MinIO's own image).

## Phase 6

Corporate/records/sanctions adapters: SEC EDGAR, GLEIF, OpenCorporates, OpenSanctions, and CourtListener. PACER, RECAP, Aleph, MuckRock, and country-specific registries remain deferred until their current access contracts are verified.

## Phase 7

The local dashboard is served at `/` by the FastAPI application. Start it with Docker Compose:

```bash
docker compose up --build -d aletheia-api
```

Then open `http://127.0.0.1:8000`. The dashboard accepts a typed seed and a required authorization assertion, starts the run through Aletheia's orchestrator, and displays the saved graph, audit tail, reports, and dossier when available. Run data is stored in `./data` on the host. Stop the service with `docker compose down`.

The Compose port is bound to loopback, and the API rejects non-local clients. Docker Desktop forwards browser requests through a gateway peer; the Compose file trusts `172.17.0.1` by default. If the local Docker gateway uses another address, set `ALETHEIA_TRUSTED_LOCAL_CLIENTS` to that exact address before starting Compose. Keep the published port bound to `127.0.0.1`; do not expose this unauthenticated operator dashboard to a public or shared network.

The benchmark store is SQLite-backed for deterministic local use. Labeled cases calculate precision, recall, coverage, and false-positive rate; unlabeled execution telemetry contributes speed and optional cost without fabricating quality scores.

The MCP bridge is a local stdio JSON-RPC service exposing investigation, resume, manifest, graph, and benchmark-leaderboard tools.
