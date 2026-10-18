# Egress proxy contract

Status: **implemented, and wired for every network-requiring adapter** (2026-10-18).
Coverage is a policy, not an allowlist: an adapter's egress is routed through the
proxy whenever its descriptor declares `network_required=True` (Phase 15). The
Phase 12 hand-wired subset (`search_engines`, `ssl_tls`, `ip_intelligence`) is now
a strict subset of that coverage. This document is the design/contract record for
the component.

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
| Wiring + tests | `app/aletheia/core/egress.py` (`ProxySession`), `tests/test_egress_wiring.py` | network + proxy lifecycle, unit-tested with an injected runner |
| End-to-end scenario | `ci/egress_scenario.py` | real-Docker `--internal` network, local origin, adapter image |
| Docker smoke | `tests/test_docker_integration.py::test_phase11_egress_proxy_container_health` | container health |
| Capture cases | `ci/capture_docker_integration.py` — `phase11-egress-proxy`, `phase12-egress-*` | raw stdout/stderr capture |

## Trust boundary and fail-closed behaviour

Adapter containers are expected to run on a Docker network with no direct route
to the internet, with `HTTP_PROXY`/`HTTPS_PROXY` pointing at the proxy. Under
that configuration a request can only leave through the proxy; when the proxy
container is down, the adapter simply has no route out. The fail-closed property
is a property of the **network**, not of application code — this is why the
Docker network wiring is part of the contract and not an optional detail.

`EgressProxy.run_command()` only *describes* the proxy container argv. The
Phase 12 wiring (`egress.ProxySession`) actually creates the network and starts
the proxy for the wired adapters; see "Wiring pattern" below.

## Wiring pattern

Wiring an adapter's egress through the proxy is one shape, applied once per
adapter run:

1. Create a fresh Docker network with `docker network create --internal
   <network>` so containers on it have **no default egress** — the proxy is the
   only route off the network.
2. Start the egress proxy detached on that network
   (`EgressProxy.run_command(..., detached=True, publish_port=False)`), so it is
   addressed by container name and never exposed on the host.
3. Run the adapter container on the *same* network with `HTTP_PROXY` and
   `HTTPS_PROXY` set to `http://<proxy-container>:<port>` (and
   `NO_PROXY=localhost,127.0.0.1` for loopback) instead of `--network bridge`.
4. After the run, read the proxy's `EGRESS.jsonl` and append it to the run's
   hash-chained audit log with `append_log_to_chain`.
5. Stop the proxy and delete the network.

`ProxySession` implements steps 1, 2, and 5; `AdapterRunRequest.proxy_url` /
`network_name` and `run_docker(..., network_name=...)` carry step 3; and the
orchestrator performs step 4. The decision for step 3 is a policy, not a list:
`egress.is_wired(name, network_required=descriptor.network_required)` is true for
every adapter that declares `network_required=True`, and `EGRESS_EXEMPT_ADAPTERS`
is the (empty) list of documented exceptions. `Orchestrator.resume` therefore wires
by default; offline replays pass `wire_egress=False`, and the CLI exposes
`--no-egress-proxy`.

Coverage is verified from the registry, not asserted: a unit test checks the
policy against all 49 adapters, and `ci/egress_scenario.py` reports a
`phase15-egress-policy-covers-registry` check plus a real-container check that
`crtsh` — an adapter outside the Phase 12 allowlist — has its egress attempt
logged by the proxy. The `phase12-*` and `phase15-*` Docker integration tests
assert those checks.

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
- Coverage is complete by policy, not by proof of every adapter's runtime
  behaviour: all 49 adapters are classified from their descriptors, and the
  proxied path is exercised end to end for `search_engines`, `ssl_tls`,
  `ip_intelligence` and `crtsh`. An adapter whose binary ignores
  `HTTP_PROXY`/`HTTPS_PROXY` (or speaks a non-HTTP protocol) would fail closed on
  the `--internal` network rather than egress unproxied, but that failure mode is
  not separately demonstrated per adapter.
- Some adapters wrap third-party CLIs (`sherlock`, `theharvester`, `amass`, …)
  that may use their own resolvers or proxy handling; the policy routes them
  through the proxy at the network level, and a client that ignores the proxy
  variables has no route out — fail-closed, not logged.

## Verification

Local: `tests/test_egress.py` plus the schema/rate-limiter/kill-switch/chain
tests, and `tests/test_project_manifest.py` (which must keep reporting **49**
Docker-invoked adapters — the proxy entry deliberately does not contain the word
`Docker` in its `invocation`, so it is not counted as an adapter).

CI: `aletheia/egress-proxy:v1` is built by `docker/build.sh`, health-checked by
the Docker integration smoke and captured by case `phase11-egress-proxy` under
`--network none`. `ci/egress_scenario.py` additionally wires the proxy, a local
origin and the adapter image onto an `--internal` Docker network and asserts the
forwarded request, the adapter's proxied egress, the audit-chain append, and the
fail-closed behaviour; those become the `phase12-egress-*` capture cases. The
status in `PROJECT_MANIFEST.json` moves from `unverified-fixture` to
`verified-fixture` only from artifact-copied lines (Gate 5).
