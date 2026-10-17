# Aletheia — Phase 7

Aletheia is a provenance-first meta-OSINT orchestration platform. Its core boundary is a typed adapter system with legal policy, checkpoints, audit events, normalized graph data, entity resolution, and provenance-preserving reports.

## Current status

**Phase 7 baseline and XposedOrNot fixture integration verified in GitHub Actions.** Run [38168341113](https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/38168341113), on commit `d9b3fe9afc9c7b28be37c8c1a5ae601c481fa59c`, reported 110 passed, `PARSER PREFLIGHT: PASS — 31/31 adapters have parser coverage`, and `DOCKER CAPTURE: PASS — 32/32 cases captured` with all capture return codes 0. This verifies fixtures and container startup only; no live XposedOrNot API lookup has been made.

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

## Audit chain

Each run's `AUDIT.jsonl` is a SHA-256 hash chain. Entries carry a sequence number, the previous entry's hash, and their own hash; the final `chain_tip` is stored in that run's `MANIFEST.json`. Verify a run with `aletheia verify-chain <RUN_ID>`. This makes changes detectable relative to the manifest anchor, but it is not a digital signature or a guarantee of legal admissibility; preserve and protect the manifest and audit files together.

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

The local web UI is served at `/` by the FastAPI application. It displays a persisted investigation graph and the benchmark leaderboard. The graph UI is intentionally local/simple and should be placed behind authentication before exposing it outside a trusted network.

The benchmark store is SQLite-backed for deterministic local use. Labeled cases calculate precision, recall, coverage, and false-positive rate; unlabeled execution telemetry contributes speed and optional cost without fabricating quality scores.

The MCP bridge is a local stdio JSON-RPC service exposing investigation, resume, manifest, graph, and benchmark-leaderboard tools.
