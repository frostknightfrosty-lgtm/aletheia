# Aletheia — Phase 7

Aletheia is a provenance-first meta-OSINT orchestration platform. Its core boundary is a typed adapter system with legal policy, checkpoints, audit events, normalized graph data, entity resolution, and provenance-preserving reports.

## Current status

**Phase 7 built; live Docker integration pending.** Docker was explicitly attempted in this environment, but the Docker CLI is not installed and no `/var/run/docker.sock` is available.

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

Finalize a completed run with entity resolution and reports:

```bash
aletheia phase2 --run-id <RUN_ID>
```

This writes `report.json`, `report.pdf`, `graph.graphml`, `report.stix2.json`, `resolution.json`, hashes, and an updated `HANDOFF.md` under the run directory.

## Phase 6

Corporate/records/sanctions adapters: SEC EDGAR, GLEIF, OpenCorporates, OpenSanctions, and CourtListener. PACER, RECAP, Aleph, MuckRock, and country-specific registries remain deferred until their current access contracts are verified.

## Phase 7

The local web UI is served at `/` by the FastAPI application. It displays a persisted investigation graph and the benchmark leaderboard. The graph UI is intentionally local/simple and should be placed behind authentication before exposing it outside a trusted network.

The benchmark store is SQLite-backed for deterministic local use. Labeled cases calculate precision, recall, coverage, and false-positive rate; unlabeled execution telemetry contributes speed and optional cost without fabricating quality scores.

The MCP bridge is a local stdio JSON-RPC service exposing investigation, resume, manifest, graph, and benchmark-leaderboard tools.
