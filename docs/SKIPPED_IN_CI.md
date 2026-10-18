# Why tests skip on a developer machine but never in CI

`AUTONOMOUS_DIRECTIVE.md` §12.10 requires zero skipped tests that were not
skipped at project start. Two groups of tests skip locally:

| Group | Count | Skip condition | Where it runs |
| --- | --- | --- | --- |
| `tests/test_docker_integration.py` | 54 | the Docker CLI is unavailable | CI (GitHub runner has Docker) |
| `tests/test_storage_services.py` | 5 | the backend's `ALETHEIA_STORAGE_*` variable is unset | CI (services started and DSNs exported) |

Skipping is correct locally: this development machine has no Docker, so there is
no daemon to run the adapter containers or the PostgreSQL/Neo4j/Elasticsearch/
S3/Redis services against.

**In CI, none of them may skip.** `ci/pytest_summary.py` enforces that. It
cross-checks two independent records of the same run and fails the job when they
disagree or when anything was skipped:

* the JUnit XML produced by `--junitxml=ci-artifacts/pytest-junit.xml`, which
  records a per-test outcome, and
* the pytest console summary line in `ci-artifacts/pytest-full.log`.

The console check exists because a module-level skip (the whole Docker file) can
be under-represented in JUnit XML; a skip visible in only one of the two records
still fails. The cross-check also catches the specific false green this is meant
to prevent: if a storage service failed to start and its environment variable was
never exported, `tests/test_storage_services.py` would skip, the suite would
report "passed", and the container verification would silently not have run.

`ci/storage_conformance.py --require-all` enforces the same rule for the storage
evidence step. The lenient default stays for developer machines; CI passes the
flag, so an unconfigured backend fails the job.

This was not theoretical. Run
[39078543221](https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39078543221)
failed to start its services (`no space left on device` while pulling the
Elasticsearch image) and the storage conformance step still reported **PASS**,
because no backend was configured and every one of them counted as skipped. The
workflow now frees disk space before building, uses non-conflicting loopback
ports, and refuses to pass when a backend is missing.

The next run,
[39079850431](https://github.com/frostknightfrosty-lgtm/aletheia/actions/runs/39079850431),
shows both gates working:

* `pytest-summary.json` recorded `junit_total: 665`, `skipped_in_ci: []` — all
  54 Docker integration tests **and** all 5 storage service tests executed;
* the log line was `2 failed, 663 passed, 1 warning`, and the two failures were
  real defects in the code (a PostgreSQL bootstrap bug and a test that asserted
  the developer machine's environment), not skips;
* the conformance step reported `STORAGE CONFORMANCE: FAIL — 5/6 backends
  conform`, naming the backend that failed instead of passing quietly.

Local skip counts are expected and are reconciled against CI on every commit:
`local passed + local skipped = CI passed`, with `CI skipped = 0`.

## Running the skipped tests

```bash
# Everything, including every Docker container and storage service, runs in CI:
# push the commit and read the `pytest-full.log`, `pytest-junit.xml` and
# `pytest-summary.json` artifacts, which must report 0 skipped.

# Locally, with Docker and the storage profile up:
docker compose --profile storage up -d
export ALETHEIA_STORAGE_POSTGRES=postgresql://aletheia:aletheia@localhost:5432/aletheia
export ALETHEIA_STORAGE_NEO4J=neo4j://neo4j:aletheia1234@localhost:7687
export ALETHEIA_STORAGE_ELASTICSEARCH=http://localhost:9200
export ALETHEIA_STORAGE_MINIO=minio://aletheia:aletheia123@localhost:9090
export ALETHEIA_STORAGE_REDIS=redis://localhost:6379/0
python -m pytest -q -rs
```
