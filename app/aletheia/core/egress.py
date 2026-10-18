"""Egress-proxy support for Aletheia.

This module is the control-plane side of the egress proxy: it knows how to start
the proxy container next to an adapter, how to point the adapter at it with
``HTTP_PROXY``/``HTTPS_PROXY``, how to read the proxy's JSONL request log, how to
apply a per-adapter token-bucket rate limit that survives a restart, how to
honour a kill switch, and how to append the logged requests to a run's
hash-chained audit log.

The proxy container itself lives in ``docker/egress_proxy`` and is a separate,
standalone component: it is not an adapter and does not appear in the adapter
registry. Adapters are expected to run on a Docker network with no direct route
to the internet, so a request can only leave through the proxy and simply fails
when the proxy is down (fail-closed at the network layer).

Honest limitation
-----------------
The audit chain the log is appended to is tamper-evident relative to a preserved
run manifest, not a digital signature, and it is not a legal-admissibility
guarantee. The proxy log records what reached the proxy; it is not proof of what
an adapter did before that point.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import UUID

from aletheia.core import chain

DEFAULT_IMAGE = "aletheia/egress-proxy:v1"
DEFAULT_PORT = 8888
LOG_FILENAME = "EGRESS.jsonl"

# Readiness probe: `docker run -d` returns before the proxy process inside has
# bound its port, so the session must wait or an adapter can lose the race and
# see "Connection refused" with no egress log at all (live run 39135219248).
PROBE_TIMEOUT_SECONDS = 15.0
PROBE_INTERVAL_SECONDS = 0.25
_PROBE_TEMPLATE = (
    "import socket,sys,time\n"
    "deadline=time.time()+{timeout}\n"
    "last=None\n"
    "while time.time()<deadline:\n"
    "    try:\n"
    "        socket.create_connection(('127.0.0.1',{port}),1).close()\n"
    "        sys.exit(0)\n"
    "    except OSError as exc:\n"
    "        last=exc\n"
    "        time.sleep({interval})\n"
    "sys.stderr.write('proxy not accepting connections: %r\\n' % (last,))\n"
    "sys.exit(1)\n"
)


def _dns_safe(name: str) -> str:
    """Make an adapter name usable as a Docker container/network DNS label."""
    safe = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in name)
    return safe.strip("-") or "adapter"

# Environment variable names shared with docker/egress_proxy/proxy.py.
ADAPTER_ENV = "ALETHEIA_ADAPTER"
PORT_ENV = "ALETHEIA_EGRESS_PORT"
LOG_PATH_ENV = "ALETHEIA_EGRESS_LOG"
KILL_SWITCH_ENV = "ALETHEIA_EGRESS_KILL_SWITCH"

# Per-request header an adapter uses to name the purpose of a request.
PURPOSE_HEADER = "X-Aletheia-Purpose"

# Every line of the proxy request log carries exactly these fields.
REQUIRED_LOG_FIELDS = (
    "timestamp",
    "adapter",
    "method",
    "host",
    "path",
    "status",
    "bytes",
    "purpose_id",
    "request_id",
)


class EgressLogError(ValueError):
    """Raised when a proxy request-log line does not match the schema."""


class EgressBlocked(RuntimeError):
    """Raised when a request is refused by the kill switch."""


def _require_str(raw: Mapping[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise EgressLogError(f"egress log field {key!r} must be a non-empty string")
    return value


def _require_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EgressLogError(f"egress log field {key!r} must be an integer")
    if value < 0:
        raise EgressLogError(f"egress log field {key!r} must be >= 0")
    return value


@dataclass(frozen=True)
class EgressLogEntry:
    """One proxied request as written by docker/egress_proxy/proxy.py."""

    timestamp: str
    adapter: str
    method: str
    host: str
    path: str
    status: int
    bytes: int
    purpose_id: str
    request_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "adapter": self.adapter,
            "method": self.method,
            "host": self.host,
            "path": self.path,
            "status": self.status,
            "bytes": self.bytes,
            "purpose_id": self.purpose_id,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "EgressLogEntry":
        if not isinstance(raw, Mapping):
            raise EgressLogError("egress log entry must be a JSON object")
        missing = [name for name in REQUIRED_LOG_FIELDS if name not in raw]
        if missing:
            raise EgressLogError("egress log entry is missing field(s): " + ", ".join(missing))
        return cls(
            timestamp=_require_str(raw, "timestamp"),
            adapter=_require_str(raw, "adapter"),
            method=_require_str(raw, "method"),
            host=_require_str(raw, "host"),
            # A CONNECT tunnel has no request path.
            path=_require_str(raw, "path", allow_empty=True),
            status=_require_int(raw, "status"),
            bytes=_require_int(raw, "bytes"),
            purpose_id=_require_str(raw, "purpose_id"),
            request_id=_require_str(raw, "request_id"),
        )


def parse_log_line(line: str) -> EgressLogEntry:
    """Parse and validate one JSONL line from the proxy request log."""
    text = line.strip()
    if not text:
        raise EgressLogError("egress log line is empty")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EgressLogError(f"egress log line is not valid JSON: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise EgressLogError("egress log line must be a JSON object")
    return EgressLogEntry.from_dict(raw)


def read_log(path: str | Path) -> list[EgressLogEntry]:
    """Read a proxy request log, skipping blank lines and naming bad lines."""
    source = Path(path)
    if not source.exists():
        return []
    entries: list[EgressLogEntry] = []
    for lineno, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(parse_log_line(line))
        except EgressLogError as exc:
            raise EgressLogError(f"{source}:{lineno}: {exc}") from exc
    return entries


@dataclass
class TokenBucket:
    """A token bucket rate limiter with an injectable clock.

    ``tokens`` and ``updated_at`` default to a full bucket at the current wall
    clock time so a reloaded bucket continues from where it stopped.
    """

    rate: float
    capacity: float
    tokens: float | None = None
    updated_at: float | None = None

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("token bucket rate must be > 0")
        if self.capacity <= 0:
            raise ValueError("token bucket capacity must be > 0")
        if self.updated_at is None:
            self.updated_at = time.time()
        if self.tokens is None:
            self.tokens = self.capacity
        self.tokens = min(self.capacity, max(0.0, float(self.tokens)))

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - float(self.updated_at))
        self.tokens = min(self.capacity, float(self.tokens) + elapsed * self.rate)
        self.updated_at = now

    def allow(self, cost: float = 1.0, *, now: float | None = None) -> bool:
        if cost <= 0:
            raise ValueError("token cost must be > 0")
        now = time.time() if now is None else float(now)
        self._refill(now)
        if float(self.tokens) >= cost:
            self.tokens = float(self.tokens) - cost
            return True
        return False

    def to_state(self) -> dict[str, float]:
        return {
            "rate": self.rate,
            "capacity": self.capacity,
            "tokens": float(self.tokens),
            "updated_at": float(self.updated_at),
        }

    @classmethod
    def from_state(cls, raw: Mapping[str, Any]) -> "TokenBucket":
        return cls(
            rate=float(raw["rate"]),
            capacity=float(raw["capacity"]),
            tokens=float(raw["tokens"]),
            updated_at=float(raw["updated_at"]),
        )


class AdapterRateLimiter:
    """One token bucket per adapter, optionally persisted to a JSON file."""

    def __init__(self, *, rate: float = 1.0, capacity: float = 1.0, state_path: str | Path | None = None) -> None:
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate limiter rate and capacity must be > 0")
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.state_path = Path(state_path) if state_path is not None else None
        self._buckets: dict[str, TokenBucket] = {}
        if self.state_path is not None and self.state_path.exists():
            self._load()

    def bucket_for(self, adapter: str, *, now: float | None = None) -> TokenBucket:
        bucket = self._buckets.get(adapter)
        if bucket is None:
            bucket = TokenBucket(self.rate, self.capacity, updated_at=now)
            self._buckets[adapter] = bucket
        return bucket

    def allow(self, adapter: str, cost: float = 1.0, *, now: float | None = None) -> bool:
        return self.bucket_for(adapter, now=now).allow(cost, now=now)

    def save(self) -> None:
        if self.state_path is None:
            return
        payload = {
            "rate": self.rate,
            "capacity": self.capacity,
            "buckets": {name: bucket.to_state() for name, bucket in self._buckets.items()},
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="egress-rate.", suffix=".tmp", dir=self.state_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.state_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _load(self) -> None:
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        for name, state in payload.get("buckets", {}).items():
            self._buckets[name] = TokenBucket.from_state(state)


class KillSwitch:
    """The single egress kill switch: an environment flag or a flag file."""

    def __init__(
        self,
        *,
        env_var: str = KILL_SWITCH_ENV,
        flag_path: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.env_var = env_var
        self.flag_path = Path(flag_path) if flag_path is not None else None
        self._environ = os.environ if environ is None else environ

    def engaged(self) -> bool:
        value = str(self._environ.get(self.env_var, "")).strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        return self.flag_path is not None and self.flag_path.exists()

    def assert_open(self) -> None:
        if self.engaged():
            raise EgressBlocked("egress kill switch is engaged")


def should_forward(
    adapter: str,
    *,
    kill_switch: KillSwitch,
    limiter: AdapterRateLimiter,
    cost: float = 1.0,
    now: float | None = None,
) -> tuple[bool, str]:
    """Decide whether one request may leave. Returns ``(allowed, reason)``."""
    if kill_switch.engaged():
        return False, "kill_switch"
    if not limiter.allow(adapter, cost, now=now):
        return False, "rate_limited"
    return True, "ok"


class EgressProxy:
    """Build the proxy container command and the adapter proxy environment.

    This is a pure description object: it runs no container itself. The Docker
    network is what actually forces adapters through the proxy; this class only
    produces the argv and the environment that wire an adapter to it.
    """

    def __init__(
        self,
        adapter: str,
        *,
        image: str = DEFAULT_IMAGE,
        port: int = DEFAULT_PORT,
        rate: float = 1.0,
        capacity: float = 1.0,
        kill_switch: bool = False,
    ) -> None:
        self.adapter = adapter
        self.image = image
        self.port = port
        self.rate = rate
        self.capacity = capacity
        self.kill_switch = kill_switch

    @property
    def container_name(self) -> str:
        # Container/DNS labels cannot carry underscores, so sanitize the name.
        return f"aletheia-egress-{_dns_safe(self.adapter)}"

    @property
    def proxy_url(self) -> str:
        return f"http://{self.container_name}:{self.port}"

    def env_for_adapter(self) -> dict[str, str]:
        return {
            "HTTP_PROXY": self.proxy_url,
            "HTTPS_PROXY": self.proxy_url,
            "http_proxy": self.proxy_url,
            "https_proxy": self.proxy_url,
            "NO_PROXY": "localhost,127.0.0.1",
            "no_proxy": "localhost,127.0.0.1",
        }

    def run_command(
        self,
        *,
        log_dir: str | Path,
        network: str | None = None,
        detached: bool = False,
        publish_port: bool = True,
    ) -> list[str]:
        command = ["docker", "run", "--rm"]
        if detached:
            command += ["-d"]
        command += ["--name", self.container_name]
        if network is not None:
            command += ["--network", network]
        command += [
            "-e", f"{ADAPTER_ENV}={self.adapter}",
            "-e", f"{PORT_ENV}={self.port}",
            "-e", f"{LOG_PATH_ENV}=/var/log/aletheia/{LOG_FILENAME}",
            "-e", f"ALETHEIA_EGRESS_RATE={self.rate}",
            "-e", f"ALETHEIA_EGRESS_BURST={self.capacity}",
        ]
        if self.kill_switch:
            command += ["-e", f"{KILL_SWITCH_ENV}=1"]
        command += [
            # Run 39119306001: Docker treats a bind-mount source as a named volume
            # unless it is an absolute path, so a relative --data-dir crashed the
            # first live wiring ("includes invalid characters for a local volume
            # name"). Resolve here, the single assembly point for this argv.
            "-v", f"{Path(log_dir).resolve()}:/var/log/aletheia",
        ]
        if publish_port:
            command += ["-p", f"{self.port}:{self.port}"]
        command += [
            self.image,
            "--serve",
        ]
        return command


def append_log_to_chain(
    run_id: str | UUID,
    entries: list[EgressLogEntry],
    *,
    data_root: str | Path | None = None,
) -> int:
    """Append each proxied request to the run's hash-chained audit log.

    Returns the number of events appended. The chain's manifest anchor and
    checkpoint hash are re-checked by ``chain.append`` on every call, so a
    tampered run refuses the append rather than recording on top of it.
    """
    count = 0
    for entry in entries:
        event = entry.to_dict()
        event["event_type"] = "egress_request"
        event["run_id"] = str(run_id)
        chain.append(event, data_root=data_root)
        count += 1
    return count


# -- wiring the proxy into adapters (Phase 12, coverage completed in Phase 15) --
#
# The wiring pattern (docs/EGRESS_PROXY_CONTRACT.md, "Wiring pattern"):
#   1. create one ``--internal`` network per adapter run: containers on it have
#      no default route out, so the proxy is the only way off the network;
#   2. start the egress proxy detached on that network, named after the adapter,
#      then attach it to the uplink (``bridge`` by default) so the proxy itself
#      has the only exit route on the host;
#   3. run the adapter on the same network with HTTP_PROXY/HTTPS_PROXY pointing
#      at the proxy and NO_PROXY for loopback;
#   4. append the proxy's request log to the run's audit chain;
#   5. stop the proxy and delete the network.
#
# Phase 12 wired three adapters through a hardcoded allowlist. Phase 15 replaced
# the allowlist with a policy: an adapter's egress goes through the proxy whenever
# its descriptor declares ``network_required=True``, which is every adapter whose
# container can reach the internet at all. Below is the (deliberately empty) list
# of documented exceptions, so an exclusion is a recorded decision rather than a
# name removed from an inclusion list.

EGRESS_EXEMPT_ADAPTERS: tuple[str, ...] = ()

NETWORK_PREFIX = "aletheia-egress"
# The proxy's second interface: the ``--internal`` adapter network has no route
# out, so the proxy — and only the proxy — reaches upstreams over this network.
UPLINK_NETWORK = "bridge"


def is_wired(adapter: str, *, network_required: bool) -> bool:
    """True when this adapter's egress must be routed through the proxy.

    ``network_required`` is the adapter descriptor's own declaration; passing it
    in keeps this module independent of the adapter registry. The rule is the
    policy, not a list: full coverage is verified for every registered adapter by
    ``tests/test_egress_wiring.py`` and by ``ci/egress_scenario.py``.
    """
    if adapter in EGRESS_EXEMPT_ADAPTERS:
        return False
    return bool(network_required)


def network_name(adapter: str) -> str:
    return f"{NETWORK_PREFIX}-net-{_dns_safe(adapter)}"


def create_network_command(network: str) -> list[str]:
    """Create an internal network (no default egress)."""
    return ["docker", "network", "create", "--internal", network]


def remove_network_command(network: str) -> list[str]:
    return ["docker", "network", "rm", network]


class DockerCommandError(RuntimeError):
    """Raised when a wiring command (network/proxy lifecycle) exits non-zero."""


def _default_runner(argv: list[str]) -> Any:
    return subprocess.run(argv, capture_output=True, text=True, timeout=120)


@dataclass
class ProxySession:
    """Bring up the internal network and the egress proxy for one adapter run.

    ``runner`` is injectable so the exact command sequence can be unit-tested
    without a Docker daemon. ``runner(argv)`` must return an object exposing
    ``returncode``, ``stdout`` and ``stderr`` (like ``subprocess.CompletedProcess``).
    """

    adapter: str
    log_dir: str | Path
    image: str = DEFAULT_IMAGE
    port: int = DEFAULT_PORT
    kill_switch: bool = False
    rate: float = 1.0
    capacity: float = 1.0
    network: str | None = None
    # Second interface for the proxy itself (see UPLINK_NETWORK).
    uplink: str = UPLINK_NETWORK
    runner: Callable[[list[str]], Any] = _default_runner
    _proxy: EgressProxy | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.log_dir = Path(self.log_dir)
        if self.network is None:
            self.network = network_name(self.adapter)
        self._proxy = EgressProxy(
            self.adapter, image=self.image, port=self.port, rate=self.rate,
            capacity=self.capacity, kill_switch=self.kill_switch,
        )

    def _run(self, argv: list[str]) -> Any:
        completed = self.runner(argv)
        code = getattr(completed, "returncode", 1)
        if code != 0:
            raise DockerCommandError(
                "wiring command failed (exit " + str(code) + "): " + " ".join(argv)
                + "\n" + (getattr(completed, "stderr", "") or "")
            )
        return completed

    def start(self) -> "ProxySession":
        """Create the internal network, start the detached proxy, uplink it, wait.

        The proxy needs the uplink interface before any adapter runs: the
        ``--internal`` adapter network has no route out, so a single-homed
        proxy cannot reach any upstream and every request would log a 502 —
        found while repairing the live path after run 39120709419, before the
        re-run could spend its budget on a proxy with no exit. The log dir is
        made world-writable because the proxy image runs as an unprivileged
        uid while the directory belongs to the orchestrator's user (same fix
        as ``ci/egress_scenario.py``). The method returns only once the proxy
        accepts TCP connections (``probe_command``): ``docker run -d``
        succeeds while the proxy process inside is still importing, and an
        adapter that fired in that window failed with "Connection refused"
        and no egress log at all (live run 39135219248, social_username).
        """
        self._run(create_network_command(self.network))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.log_dir, 0o777)
        argv = self._proxy.run_command(
            log_dir=self.log_dir, network=self.network, detached=True, publish_port=False
        )
        self._run(argv)
        # Attach the uplink last: the proxy is the only container that may use
        # it, and no adapter has started yet when this command returns.
        self._run(["docker", "network", "connect", self.uplink, self._proxy.container_name])
        try:
            self._run(self.probe_command())
        except DockerCommandError as exc:
            raise DockerCommandError(
                "egress proxy " + self._proxy.container_name
                + " did not accept a TCP connection within the readiness window\n" + str(exc)
            ) from exc
        return self

    def probe_command(self) -> list[str]:
        """An exec that retries a loopback connect until the proxy listens.

        Runs a bounded python one-liner inside the proxy container itself, so
        it needs neither a published port (the live path publishes none) nor
        the uplink: it asks the only question that matters before an adapter
        starts - is the listening socket there yet.
        """
        code = _PROBE_TEMPLATE.format(
            timeout=PROBE_TIMEOUT_SECONDS, port=self.port, interval=PROBE_INTERVAL_SECONDS
        )
        return ["docker", "exec", self._proxy.container_name, "python", "-c", code]

    @property
    def proxy_url(self) -> str:
        return self._proxy.proxy_url

    @property
    def proxy_container(self) -> str:
        return self._proxy.container_name

    @property
    def log_path(self) -> Path:
        return self.log_dir / LOG_FILENAME

    def read_entries(self) -> list[EgressLogEntry]:
        return read_log(self.log_path)

    def stop(self) -> None:
        """Stop the proxy and remove the network; never raises."""
        for argv in (
            ["docker", "rm", "-f", self._proxy.container_name],
            remove_network_command(self.network),
        ):
            try:
                self.runner(argv)
            except Exception:
                pass

    def __enter__(self) -> "ProxySession":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

