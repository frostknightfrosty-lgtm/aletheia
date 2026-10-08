# Phase 4 Validation

## Local validation

- Unit/contract/API/security suite: **41 passed**.
- Docker integration suite: **20 skipped** because the environment has neither the Docker CLI nor `/var/run/docker.sock`.
- `python -m compileall -q app docker`: passed.
- `bash -n docker/build.sh`: passed.
- API `/healthz`: reports phase 4.
- Secret propagation test: passed; secret values are not placed in Docker argv or audit command records.

## Docker attempt

Docker was explicitly attempted rather than assumed unavailable. The build command:

```text
./docker/build.sh
```

returned exit code **127** with:

```text
./docker/build.sh: line 4: docker: command not found
```

A filesystem check also found no `/var/run/docker.sock`. The Docker-only pytest suite therefore skips all 20 live container tests rather than substituting mocked results.

## Reproduce on a Docker host

```bash
./docker/build.sh
pytest -q -m integration
```

The 20 integration tests cover the 3 original containers, 10 Phase 3 containers, and 7 Phase 4 containers.
