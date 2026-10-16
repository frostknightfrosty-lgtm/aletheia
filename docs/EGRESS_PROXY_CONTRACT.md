# Egress proxy contract

Status: **implemented as a standalone component** (2026-10-16). Not yet wired
into every adapter's Dockerfile — that is a separate session. This document is
the design/contract record for the component; it was missing from the repository
before this session and is created here.

## Purpose

Force every adapter's outbound HTTP/HTTPS request through one local proxy that:

- logs each request (adapter, method, host, path, status, bytes, purpose id,
  request id, timestamp);
- enforces a per-adapter rate limit;
- provides a single kill switch;
- fails closed: if the proxy is down, adapters cannot reach the internet.

The proxy is **infrastructure**, not an adapter. It does not appear in the
adapter registry and does not carry `parser_test` coverage.

## Components

| Piece | Path | Role |
| --- | --- | --- |
| Control-plane module | `app/aletheia/core/egress.py` | log reader, rate limiter, kill switch, lifecycle/env helpers, chain writer |
| Forwarder | `docker/egress_proxy/proxy.py` | the proxy process (standard library only) |
| Image | `docker/egress_proxy/Dockerfile` | `aletheia/egress-proxy:v1` |
| Fixture | `tests/fixtures/egress_proxy_log.jsonl` | synthetic request log |
| Tests | `tests/test_egress.py` | schema, rate limiter, kill switch, helpers, chain writer |
| Docker smoke | `tests/test_docker_integration.py::test_phase11_egress_proxy_container_health` | container health |
| Capture case | `ci/capture_docker_integration.py` — `phase11-egress-proxy` | raw stdout/stderr capture |

## Trust boundary and fail-closed behaviour

Adapter containers are expected to run on a Docker network with no direct route
to the internet, with `HTTP_PROXY`/`HTTPS_PROXY` pointing at the proxy. Under
that configuration a request can only leave through the proxy; when the proxy
container is down, the adapter simply has no route out. The fail-closed property
is a property of the **network**, not of application code — this is why the
Docker network wiring is part of the contract and not an optional detail.

`EgressProxy.run_command()` only *describes* the proxy container argv; the
repository does not yet start it for every adapter. This component prepares that
wiring.

## Request log schema

The proxy writes one JSON object per line to `ALETHEIA_EGRESS_LOG`
(default `/var/log/aletheia/EGRESS.jsonl`). Every line has exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `timestamp` | string | ISO-8601 UTC time the request was logged |
| `adapter` | string | adapter that made the request (`ALETHEIA_ADAPTER`) |
| `method` | string | HTTP method, or `CONNECT` for a tunnel |
| `host` | string | target host |
| `path` | string | request path (empty for `CONNECT`) |
| `status` | int ≥ 0 | upstream status, or `403`/`429`/`502` for refused/failed requests |
| `bytes` | int ≥ 0 | response bytes returned to the adapter |
| `purpose_id` | string | from the `X-Aletheia-Purpose` request header, else `unspecified` |
| `request_id` | string | unique per request |

`app/aletheia/core/egress.py::read_log` validates every line and raises
`EgressLogError` naming the file and line number on a malformed entry.

The log stores **metadata only** — no request or response bodies and no
credentials.

## Rate limiting

Per-adapter token bucket, persisted across restarts:

- `TokenBucket(rate, capacity)` with an injectable clock; `allow()` refills by
  elapsed time and denies when short.
- `AdapterRateLimiter(rate, capacity, state_path)` keeps one bucket per adapter
  and writes/reads a JSON state file atomically.
- `should_forward(adapter, kill_switch=…, limiter=…) -> (allowed, reason)` where
  reason is `"ok"`, `"kill_switch"`, or `"rate_limited"`.

The proxy applies the same decision before opening any upstream connection and
logs refusals with status `429`.

## Kill switch

`KillSwitch(env_var="ALETHEIA_EGRESS_KILL_SWITCH", flag_path=…)` is engaged when
the environment value is truthy (`1`/`true`/`yes`/`on`) **or** the flag file
exists. An engaged switch blocks every request (status `403`) and
`assert_open()` raises `EgressBlocked`.

## Audit-chain integration

`append_log_to_chain(run_id, entries, data_root=…)` appends each request as an
`egress_request` event to the run's hash-chained `AUDIT.jsonl` through
`aletheia.core.chain.append`. Because `chain.append` re-checks the run manifest's
`chain_tip` anchor and `checkpoint_hash` on every call, a tampered run refuses
the append instead of recording on top of the tampered chain.

## Honest limitations

- The chain is **tamper-evident relative to a preserved run manifest**, not a
  digital signature, and not a legal-admissibility guarantee.
- The proxy log records what reached the proxy. It is not proof of what an
  adapter did before that point, and it cannot see inside an already-tunnelled
  TLS session.
- The forwarding loop is exercised only in Docker/CI. Only the pure helpers and
  the request-log schema are unit-tested locally.
- The proxy is not yet started for every adapter; adapter Dockerfiles and the
  run-time network wiring are still to be changed in a later session.

## Verification

Local: `tests/test_egress.py` plus the schema/rate-limiter/kill-switch/chain
tests, and `tests/test_project_manifest.py` (which must keep reporting **49**
Docker-invoked adapters — the proxy entry deliberately does not contain the word
`Docker` in its `invocation`, so it is not counted as an adapter).

CI: `aletheia/egress-proxy:v1` is built by `docker/build.sh`, health-checked by
the Docker integration smoke and captured by case `phase11-egress-proxy` under
`--network none`. The status in `PROJECT_MANIFEST.json` moves from
`unverified-fixture` to `verified-fixture` only from artifact-copied lines
(Gate 5).
