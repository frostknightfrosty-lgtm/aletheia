# Aletheia — CI_READY

This document is the zero-to-full verification procedure for the current Step 3 checkpoint. It is intentionally limited to the existing 34 Docker integration cases plus the existing local regression suite. It does not perform a live OSINT investigation and it does not require any real target credentials.

## 1. Prereqs

**Primary environment:** Linux x86_64/amd64, preferably Ubuntu 24.04 LTS or 22.04 LTS, with a normal Docker Engine daemon and Docker Compose v2. The Docker project officially supports those Ubuntu releases and amd64/arm64; this checkpoint's recommended verification environment is amd64 because the full dependency matrix has not been live-verified on arm64. Docker Desktop is acceptable on macOS/Windows, preferably through a Linux VM/WSL2 path. See Docker's current installation requirements: https://docs.docker.com/engine/install/ubuntu/

**Docker floor:** Docker Engine 29.1.4+ is the project-set floor for the verification run. This is a conservative project floor, not a claim that older Docker versions cannot run the code. Docker 29.1.4 specifically fixed a `--network none` regression on Windows. A newer Docker Engine is preferred. Docker's current 29.x release notes are here: https://docs.docker.com/engine/release-notes/29

**Compose:** Docker Compose v2 with `docker compose` available. On Linux, use the official Docker package that includes `docker-compose-plugin`; on Docker Desktop it is bundled.

**Resources:** 8 GB RAM minimum; 12 GB recommended. 30 GB free disk is the project-set minimum for the complete sequential build; 50 GB is recommended. The large images are the Go toolchains and the ML/Python stacks. These are operational project floors, not vendor minimums.

**Network egress:** required for building the images and installing test dependencies, but **not** for the 34 Docker integration executions themselves because they use `--network none`.

Expected build/install hosts include:
- Docker Hub: `registry-1.docker.io`, `auth.docker.io`, Docker layer/CDN hosts.
- Docker static CLI: `download.docker.com`.
- Python packages: `pypi.org`, `files.pythonhosted.org`.
- Go modules/source: `proxy.golang.org`, `sum.golang.org`, `github.com`.
- Node packages: `registry.npmjs.org`.
- Debian packages: `deb.debian.org`, `security.debian.org`.
- Alpine packages: `dl-cdn.alpinelinux.org`.

No third-party OSINT API endpoint is intentionally contacted by the Docker integration cases; the health commands are isolated with `--network none`.

**Estimated wall time:** 45–120 minutes on a modern desktop/server with warm network caches; cold ML/package builds may run longer. The full run is therefore given a two-hour CI timeout.

## 2. Clone and checkout

There is no pre-existing upstream Git remote URL in this sandbox checkpoint. To make the exact source tree reproducible, this checkpoint includes a Git bundle containing the tagged commit `step3-ci-ready`.

1. Download these two files from the checkpoint: the Step 3 source ZIP and the accompanying Git bundle.
2. Verify the source ZIP SHA-256 against the value published with the checkpoint:

```bash
sha256sum aletheia_step3_ci_ready.zip
# Expected: fa2cff45063e9ecf79aadefdbbb9db29a56b2eac8861d879757dc0e38edaf787
```

3. Clone the Git bundle:

```bash
git clone --branch step3-ci-ready ./aletheia_step3_ci_ready.bundle aletheia
cd aletheia
git rev-parse HEAD
git status --short
```

The checkpoint commit SHA is **f0e53587f2a15160812cb70f26e403b0461646ed**. The checkout must have an empty git status and `git rev-parse HEAD` must equal `f0e53587f2a15160812cb70f26e403b0461646ed`.

4. Verify that the checked-out Git object reproduces the published source ZIP:

```bash
git archive --format=zip --prefix=aletheia_step3_ci_ready/ -o /tmp/aletheia-recreated.zip HEAD
sha256sum /tmp/aletheia-recreated.zip
```

The SHA-256 must equal the published checkpoint ZIP SHA-256. A mismatch means stop and capture the two hashes; do not proceed.

**Self-reference note:** this finalized CI_READY copy is delivered as release metadata outside the Git tree, so it can state the exact commit SHA without making the Git commit self-referential. The source tree uses the `step3-ci-ready` ref; `git archive` from the exact commit reproduces the published source ZIP hash exactly.

## 3. Env vars

For the Docker verification suite, **no environment variable is required**. The 34 Docker tests use only local image health/import commands and `--network none`. Do not provide real OSINT credentials for this run.

| Variable | Classification | Safe default | Effect if unset |
|---|---|---|---|
| `ALETHEIA_DATA_DIR` | optional | unset | Uses application default; not needed by Docker health tests. |
| `ALETHEIA_HTTP_PROXY` | optional | unset | No proxy environment is injected. This is expected because the egress proxy is not yet implemented. |
| `HIBP_API_KEY` | triggers-skip-if-missing for future HIBP live work; **not used by current Docker test** | unset | No HIBP API call is attempted. The current HIBP `--health` case still runs. |
| `TWILIO_API_KEY` | triggers-skip-if-missing for future Twilio live work; **not used by current Docker test** | unset | No Twilio API call is attempted. The current Twilio `--health` case still runs. |
| `TWILIO_API_SECRET` | triggers-skip-if-missing for future Twilio live work; **not used by current Docker test** | unset | No Twilio API call is attempted. |
| `SHODAN_API_KEY` | triggers-skip-if-missing for future Shodan live work; **not used by current Docker test** | unset | No Shodan API call is attempted. The current Shodan `--health` case still runs. |
| `CENSYS_API_TOKEN` | triggers-skip-if-missing for future Censys live work; **not used by current Docker test** | unset | No Censys API call is attempted. The current Censys `--health` case still runs. |
| `CENSYS_ORG_ID` | optional dependency of future Censys org-scoped calls | unset | Uses token-only health path; no live API call is attempted in this suite. |
| `REDDIT_CLIENT_ID` | triggers-skip-if-missing for future Reddit live work; **not used by current Docker test** | unset | No Reddit API call is attempted. |
| `REDDIT_CLIENT_SECRET` | triggers-skip-if-missing for future Reddit live work; **not used by current Docker test** | unset | No Reddit API call is attempted. |
| `REDDIT_USER_AGENT` | optional | `Aletheia/0.5.0` | Only affects future Reddit API requests; current health case is offline. |
| `YOUTUBE_API_KEY` | triggers-skip-if-missing for future YouTube live work; **not used by current Docker test** | unset | No YouTube API call is attempted. |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | triggers-skip-if-missing for future Google Vision live work; **not used by current Docker test** | unset | No Google Vision API call is attempted. |
| `DOCKER_HOST` | optional | unset | Docker CLI uses its normal local socket/context. Set it only when intentionally using a remote daemon. |
| `GITHUB_TOKEN` | optional, act fallback only | unset | `act` supplies its normal local workflow context; no external API credentials are required for these jobs. |

Loud required-variable check for this run:

```bash
required_vars=()
for v in "${required_vars[@]}"; do
  [[ -n "${!v:-}" ]] || { echo "MISSING REQUIRED ENV: $v" >&2; exit 1; }
done
echo "ENV PREFLIGHT: PASS — no required CI secrets for this suite"
```

## 4. Recommended runner: plain Docker Compose

**Recommendation: plain Docker Compose.** It uses the real Docker daemon directly and does not introduce GitHub Actions emulation or a second artifact-server implementation into the critical path. The repository includes a dedicated verification-runner compose override that provides Python plus the Docker CLI, mounts the real Docker socket, builds every tagged adapter image, runs the full pytest suite, captures raw Docker stdout/stderr, and writes local evidence.

**Fallback: `act`.** `act` is useful when you specifically want to execute the exact GitHub Actions YAML locally, but its artifact-server compatibility is not identical to GitHub's service; therefore it is the fallback rather than the primary verification path. Current `act` is v0.2.89: https://github.com/nektos/act/releases

## 5. Verify GitHub Actions action versions first

The current confirmed stable majors are:

- `actions/checkout@v7` — latest major; current marketplace/release is v7.0.1.
- `actions/setup-python@v7` — latest major; current marketplace/release is v7.0.0.
- `actions/upload-artifact@v7` — latest major; current release is v7.0.2.

The workflow originally used `upload-artifact@v4`; that pin was corrected to **v7**. No other workflow semantics were changed.

## 6. Commands

### Recommended path — Docker Compose

From the repository root:

```bash
set -euo pipefail

docker --version
docker compose version
docker info >/tmp/aletheia-docker-info.txt

rm -rf docker/verification-artifacts
mkdir -p docker/verification-artifacts

docker compose -f docker/docker-compose.verification.yml build verification-runner

docker compose -f docker/docker-compose.verification.yml run --rm verification-runner
```

The runner writes evidence under `docker/verification-artifacts/`.

### Fallback path — `act`

Install current `act` v0.2.89 using the official installer, then from the repository root:

```bash
curl -s https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
act --version
rm -rf act-artifacts
mkdir -p act-artifacts
act workflow_dispatch \\
  -W .github/workflows/docker-verification.yml \\
  --artifact-server-path ./act-artifacts \\
  -P ubuntu-latest=catthehacker/ubuntu:act-latest
```

The workflow's own `ci-artifacts/` files remain the authoritative local evidence; `act-artifacts/` is the local artifact-server output.

### Five-minute smoke test

Before either full run:

```bash
set -euo pipefail
docker run --rm hello-world >/tmp/aletheia-docker-smoke.txt
docker --version
docker info >/tmp/aletheia-docker-info-smoke.txt
echo "DOCKER SMOKE: PASS"
```

If this fails, capture the two files plus the command output and stop. Do not start the full run.

## 7. What "pass" looks like

For the complete suite, look for all of these literal lines:

```text
PARSER PREFLIGHT: PASS — 33/33 adapters have parser coverage
```

```text
111 passed in
```

For the evidence-capture helper:

```text
DOCKER CAPTURE: PASS — 34/34 cases captured
```

For the Compose harness only:

```text
CI READY HARNESS: PASS
```

Expected process exit code: **0**. The Compose harness additionally creates:

```text
ci-artifacts/CI_SUCCESS
```

The GitHub Actions workflow itself does not currently write a success sentinel; its success condition is the job exit status plus the literal test/pre-flight lines above.

## 8. What failure looks like

| Failure class | Likely first symptom | Distinguish from environment problem | Capture |
|---|---|---|---|
| Image build failure | `docker build` non-zero; package/download/build error names a Dockerfile step | `docker info` and `hello-world` succeed, and the failure occurs inside a specific build step | `ci-artifacts/docker-build.log`, image/Dockerfile hash record, failing Dockerfile path |
| Dependency install failure | pip/npm/go/apt/alpine install returns non-zero | Docker daemon works and failure is reproducible inside the named image build step | Full build log plus exact package/version message |
| Container launch failure | `docker run` returns non-zero before expected health text | `docker image inspect IMAGE` succeeds and the failure is at container start/entrypoint | Per-case `.stdout`, `.stderr`, command from `results.json`, `docker image inspect` output |
| Adapter execution failure | Container starts but command exits non-zero or emits an explicit adapter error | Image exists and a minimal `hello-world` Docker smoke passed | Per-case raw stdout/stderr, exit code, image ID |
| Adapter output parse failure | Docker case may pass, but a parser fixture assertion fails in pytest | Parser pre-flight and Docker runtime are healthy; failure points to a named test and fixture | `pytest-full.log`, fixture file, traceback, adapter parser test name |
| Orchestration failure | pytest collection/runtime error, checkpoint/graph assertion failure, or harness script exception | Individual Docker cases can pass while the application test fails | `pytest-full.log`, parser pre-flight, harness output, git SHA |

**Capture and stop** on failure. Do not retry before preserving the first failing evidence set.

## 9. Artifacts to collect

After a successful recommended run, expect:

```text
ci-artifacts/parser-preflight.txt
ci-artifacts/docker-build.log
ci-artifacts/image-ids-and-dockerfile-sha256.txt
ci-artifacts/pytest-full.log
ci-artifacts/docker-integration/capture.log
ci-artifacts/docker-integration/results.json
ci-artifacts/docker-integration/*.stdout
ci-artifacts/docker-integration/*.stderr
ci-artifacts/CI_SUCCESS
```

For the GitHub Actions path also collect:

```text
docker-runtime.txt
ci-parser-preflight.txt
```

Bundle the evidence in one timestamped archive:

```bash
ts=$(date -u +%Y%m%dT%H%M%SZ)
tar -czf "aletheia-ci-${ts}.tar.gz" \\
  ci-artifacts \\
  docker-runtime.txt \\
  ci-parser-preflight.txt 2>/dev/null || true
sha256sum "aletheia-ci-${ts}.tar.gz"
```

Expected evidence archive size: **roughly 5–100 MB**, dominated by build logs; raw adapter outputs themselves should be small. Do not include credentials, Docker registry auth files, or unrelated home-directory material.

## 10. What the CI run proves and does not prove

A successful CI run proves that the tagged Docker images can be built, the containers can be launched, the current 34 container smoke commands produce captured raw output, and the 33 parser fixture tests remain green; it does **not** prove real-world OSINT correctness, live target behavior, legal compliance in a real jurisdiction, the non-existent egress proxy, or the requested SIGKILL/resume scenario. The current workflow has no truthful way to claim proxy logging or kill/restart proof because those components are not yet implemented; those remain explicit Phase 8 verification gates, after the CI run passes and before any live authorized investigation.

## Appendix A — 34-test checklist

Each line identifies exactly what a pass proves and the most likely meaning of failure.

1. `phase1-sherlock`: proves the Sherlock image builds and its `--version` entrypoint executes; failure most likely means image build/dependency/entrypoint drift.
2. `phase1-theharvester`: proves the theHarvester image builds and its help entrypoint executes; failure most likely means package/version or entrypoint drift.
3. `phase1-exiftool`: proves ExifTool runs in an isolated no-network container and emits JSON metadata for a mounted file; failure most likely means image/package/mount or CLI drift.
4. `phase3-amass`: proves the pinned Amass binary starts in its image; failure most likely means Go build or CLI packaging drift.
5. `phase3-subfinder`: proves the pinned Subfinder binary starts in its image; failure most likely means Go build or CLI packaging drift.
6. `phase3-assetfinder`: proves Assetfinder's pinned image starts and exposes help; failure most likely means Go build or CLI packaging drift.
7. `phase3-dnsx`: proves the pinned DNSX binary starts; failure most likely means Go build or CLI packaging drift.
8. `phase3-massdns`: proves MassDNS starts from its multi-stage image; failure most likely means source clone/build or entrypoint drift.
9. `phase3-dnsrecon`: proves DNSRecon's pinned Python package starts; failure most likely means package dependency or console-entrypoint drift.
10. `phase3-fierce`: proves Fierce's pinned Python package starts; failure most likely means package dependency or console-entrypoint drift.
11. `phase3-shodan`: proves the Shodan runner responds to its offline health command; failure most likely means runner import/version or CLI wrapper drift.
12. `phase3-censys`: proves the Censys runner responds to its offline health command; failure most likely means SDK/runner wiring drift.
13. `phase3-crtsh`: proves the crt.sh runner responds to its offline health command; failure most likely means runner packaging drift.
14. `phase4-maigret`: proves Maigret's pinned image and CLI start; failure most likely means package/version or entrypoint drift.
15. `phase4-holehe`: proves Holehe's pinned image and help command start; failure most likely means package/version or entrypoint drift.
16. `phase4-h8mail`: proves h8mail's pinned image and help command start; failure most likely means package/version or entrypoint drift.
17. `phase4-hibp`: proves the HIBP API runner can start in offline health mode without a key; failure most likely means runner packaging drift.
18. `phase4-phoneinfoga`: proves PhoneInfoga's pinned binary runs; failure most likely means downloaded binary architecture/version drift.
19. `phase4-libphonenumber`: proves the offline phone-number runner starts without network; failure most likely means Python package/runtime drift.
20. `phase4-twilio`: proves the Twilio runner starts in offline health mode; failure most likely means runner packaging drift.
21. `phase5-instaloader`: proves the Instaloader wrapper starts without reaching the network; failure most likely means package/runtime drift.
22. `phase5-reddit`: proves the Reddit API runner loads and its health path works offline; failure most likely means runner dependency drift.
23. `phase5-youtube`: proves the YouTube API runner loads and its health path works offline; failure most likely means runner dependency drift.
24. `phase5-overpass`: proves the Overpass runner loads and its health path works offline; failure most likely means runner packaging drift.
25. `phase5-suncalc`: proves the Node/SunCalc wrapper starts without network; failure most likely means npm dependency drift.
26. `phase5-deepface`: proves the DeepFace image builds and its wrapper health path starts; failure most likely means ML dependency/wheel drift.
27. `phase5-insightface`: proves the InsightFace image builds and its wrapper health path starts; failure most likely means ML dependency/wheel drift.
28. `phase5-google-vision`: proves the Google Vision wrapper starts without credentials in health mode; failure most likely means SDK/runtime drift.
29. `phase6-sec-edgar`: proves the SEC EDGAR runner starts in offline health mode; failure most likely means runner packaging drift.
30. `phase6-gleif`: proves the GLEIF runner starts in offline health mode; failure most likely means runner packaging drift.
31. `phase6-opencorporates`: proves the OpenCorporates runner starts in offline health mode; failure most likely means runner packaging drift.
32. `phase6-opensanctions`: proves the OpenSanctions runner starts in offline health mode; failure most likely means runner packaging drift.
33. `phase6-courtlistener`: proves the CourtListener runner starts in offline health mode; failure most likely means runner packaging drift.
34. `phase7-core-import`: proves the core Aletheia image builds and imports the application package; failure most likely means packaging/runtime dependency drift.
