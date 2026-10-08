# Phase 6 Validation

- Application/unit/parser/security tests: **59 passed**.
- Docker-only health tests: **33 skipped** because Docker CLI and `/var/run/docker.sock` are unavailable.
- `pytest -q -m integration`: **33 skipped, 59 deselected**.
- `python -m compileall -q app docker`: passed.
- `bash -n docker/build.sh`: passed.
- Explicit Docker build attempt: `./docker/build.sh` exit code **127** with `docker: command not found`.
- `/var/run/docker.sock`: absent.

No live corporate/records/sanctions lookup was performed in this validation environment.
