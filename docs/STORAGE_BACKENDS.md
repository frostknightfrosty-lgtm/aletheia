# Storage Backends (Phase 14)

Phase 14 adds a portable persistence contract for the two artefacts the audit
trail names — **graph snapshots** (`GraphStore`) and **run manifests**
(`CheckpointStore`) — and implements it on five networked backends plus the
default file store.

Status: **implemented and CI-verified** for `file`, `postgres`, `neo4j`,
`elasticsearch`, `minio` (S3 API), and `redis`. See "Verification" below for how
each is proven and "Honest limits" for what is *not* claimed.

## The contract

`app/aletheia/storage/base.py` defines `StorageBackend`, an ABC with these
operations:

| Operation | Meaning |
| --- | --- |
| `save_graph(run_id, graph) -> str` | Persist a graph snapshot (JSON object); return a backend-local locator. |
| `load_graph(run_id) -> dict \| None` | Return the stored graph, or `None` when absent. |
| `save_manifest(run_id, manifest)` | Persist a run manifest, replacing any previous value. |
| `load_manifest(run_id) -> dict \| None` | Return the stored manifest, or `None` when absent. |
| `list_runs() -> list[str]` | Sorted run ids that have a graph or a manifest. |
| `health() -> dict` | `{"backend", "ok", ...}`; never raises. |
| `migrations()` / `apply_migration()` | This backend's ordered migrations and their effect. |
| `applied_migrations()` / `record_migration()` | Version-tracking state. |
| `close()` | Release a held connection (idempotent). |

The contract is JSON-document oriented so a graph exported by the pipeline
round-trips byte-for-byte through any backend. A graph database backend may
*additionally* materialise entities and edges; that is an extension, not a
requirement (see Neo4j below).

`FileGraphStore` implements the whole contract and keeps its historical
`root` attribute, so the API (`app/aletheia/api/app.py`) and orchestrator
(`app/aletheia/core/orchestrator.py`) continue to address
`<root>/<run_id>/graph.json` unchanged.

## Backends

| Name | Environment variable | Where documents live | Durability |
| --- | --- | --- | --- |
| `file` | (default; `--data-dir`) | `<root>/<run_id>/graph.json`, `MANIFEST.json` | durable local disk |
| `postgres` | `ALETHEIA_STORAGE_POSTGRES` | JSONB rows in `aletheia_graphs` / `aletheia_manifests` | durable (RDBMS, WAL) |
| `neo4j` | `ALETHEIA_STORAGE_NEO4J` | JSON snapshot on `(:AletheiaGraph)` **and** entities/edges as `(:AletheiaEntity)` + `[:RELATED]` | durable |
| `elasticsearch` | `ALETHEIA_STORAGE_ELASTICSEARCH` | documents in `aletheia-graphs` / `aletheia-manifests`, with a field-search capability | durable (with replicas) |
| `minio` (S3 API) | `ALETHEIA_STORAGE_MINIO` | one JSON object per run in `aletheia-graphs` / `aletheia-manifests` | durable (object store) |
| `redis` | `ALETHEIA_STORAGE_REDIS` | `aletheia:graph:<run_id>` / `aletheia:manifest:<run_id>` keys | **server-dependent** (RDB/AOF); treat as a cache, not a system of record |

DSN format is `scheme://user:password@host:port/database`, e.g.
`postgresql://aletheia:aletheia@localhost:5432/aletheia`,
`neo4j://neo4j:password@localhost:7687`,
`minio://access:secret@localhost:9000`. Drivers are in the `storage`
extra: `pip install -e '.[storage]'`.

### Neo4j is a real graph backend

`Neo4jBackend.save_graph` does two things: it stores the canonical JSON
snapshot (so round-trip equality holds) **and** materialises the graph:

```cypher
MERGE (n:AletheiaEntity {run_id: $run_id, entity_id: e.entity_id}) ...
MERGE (a)-[r:RELATED {run_id: $run_id, edge_id: x.edge_id}]->(b) ...
```

`verify_materialised(run_id, entities, edges)` is the conformance hook that
asserts the node/relationship counts match the snapshot, which is what
distinguishes this from an object store with a Cypher front end.

## Migration runner

`MigrationRunner(backend).run()` applies every migration whose version is not
recorded, in version order, and records `(version, name, checksum, applied_at)`.
The checksum is derived from the migration's version, name, and statement, so a
silently edited migration is refused:

* second run is a no-op (`applied_now == []`);
* a changed checksum or name on an already-applied migration raises
  `MigrationError` (drift detection).

`status()` reports `applied` and `pending` versions. Each backend owns its
migration list (SQL DDL for Postgres, Cypher constraints for Neo4j, index
mappings for Elasticsearch, bucket creation for S3, and a namespace reservation
for Redis, which is schema-less).

## CLI

```bash
aletheia storage health [--backend NAME] [--data-dir DIR]
aletheia storage migrate --backend NAME [--target DSN]
aletheia storage sync --run-id UUID --backend NAME [--target DSN]
```

* `health` probes the file store and every requested/configured backend; a
  backend with no DSN is reported `"configured": false` rather than omitted.
* `migrate` runs the migration runner and prints `applied_now` / `applied_total`.
* `sync` copies a run's graph and manifest from the file store into the backend
  and asserts a round-trip read-back matches. **The file store remains
  authoritative**; `sync` mirrors, it does not migrate ownership.

## Verification

The conformance contract lives in `app/aletheia/storage/conformance.py` and is
shared by two callers so they cannot drift:

* `tests/test_storage.py` (always runs locally): migration-runner semantics, the
  file backend, the factory, the Redis backend against `fakeredis`, and a
  **negative control** (`BrokenBackend`) asserting the contract fails on a
  backend that returns the wrong graph.
* `tests/test_storage_services.py`: the same contract against each real
  service. A backend is skipped **only** when its environment variable is unset;
  in CI every variable is set, so a backend that will not connect fails the
  suite instead of skipping.
* `ci/storage_conformance.py` runs the contract against the file store plus
  every configured service and writes `ci-artifacts/storage-conformance.json`.
  CI invokes it with `--require-all`, so a backend whose service never started
  makes the step fail instead of being quietly reported as unconfigured.

`.github/workflows/docker-verification.yml` frees space for the service images,
starts PostgreSQL, Redis, Neo4j, Elasticsearch, and an S3-protocol server,
exports the DSNs, and runs both the suite and the evidence script.

## Honest limits

* **MinIO image availability.** MinIO removed `minio/minio` from Docker Hub and
  `quay.io/minio/minio` no longer allows anonymous pulls (September 2026). The
  `minio` backend speaks the S3 API through `minio-py`, and CI verifies it
  against the S3-protocol server `adobe/s3mock`. A real MinIO (or any S3
  endpoint) is used unchanged by setting `ALETHEIA_STORAGE_MINIO`. This is an S3
  *protocol* verification, not a MinIO *server* verification.
* **The audit chain is not moved onto these backends.** `AUDIT.jsonl` and the
  per-run directory (handoff, per-adapter artefacts) stay on the local file
  store. The chain's tamper-evidence depends on atomic `fsync` appends to a
  single file; moving it onto an eventually-consistent store would weaken the
  property, so it is deliberately out of scope.
* **The pipeline is not yet switched to a networked backend by default.** The
  orchestrator still writes through `FileGraphStore`; networked backends are
  populated via `aletheia storage sync` / the Python API. Wiring the pipeline to
  a backend selected by environment is future work.
* **Redis is a cache.** Its durability is exactly whatever the server's
  persistence configuration provides; it is documented as a fast path, not a
  system of record.
* **Checksum drift is intentional.** Editing an already-applied migration's text
  will (correctly) make `MigrationRunner.run()` raise until the recorded row for
  that version is reconciled. On a fresh CI service this never occurs.
