#!/usr/bin/env python3
"""Aletheia egress proxy — a standalone forward HTTP/HTTPS proxy.

Adapter containers are pointed at this proxy with ``HTTP_PROXY``/``HTTPS_PROXY``
and are meant to run on a Docker network with no direct route to the internet,
so every outbound request can only leave through here. When the proxy is down,
adapters simply cannot reach the network (fail-closed at the network layer).

What it does
------------
- Plain HTTP: accepts an absolute-form request target (``GET http://host/path``),
  forwards it, and logs method/host/path/status/bytes.
- HTTPS: accepts ``CONNECT host:port``, replies ``200 Connection Established``,
  and tunnels bytes; the tunnel is logged once when it closes.
- Applies a per-adapter token bucket and a kill switch before any connection is
  opened. A refused request is logged with status 403 (kill switch) or 429
  (rate limited).

Configuration (environment)
---------------------------
``ALETHEIA_ADAPTER``          adapter name recorded on every log line.
``ALETHEIA_EGRESS_PORT``      listen port (default 8888).
``ALETHEIA_EGRESS_LOG``       JSONL request log path.
``ALETHEIA_EGRESS_KILL_SWITCH``  truthy value blocks every request.
``ALETHEIA_EGRESS_RATE``      sustained tokens/second per adapter (default 1).
``ALETHEIA_EGRESS_BURST``     bucket capacity per adapter (default 1).

The image installs no third-party package: the standard library only.

``--health`` prints exactly ``ok`` on stdout and returns 0 without opening a
socket, so the Docker integration smoke can run it under ``--network none``.

Scope note
----------
This component is not an adapter and is not wired into every adapter's
Dockerfile yet. The forwarding loop is exercised only inside Docker/CI; the pure
helpers below (``parse_request_line``, ``host_port_from_target``,
``make_log_record``, ``TokenBucket``) are unit-tested locally.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

DEFAULT_PORT = 8888
DEFAULT_LOG = "/var/log/aletheia/EGRESS.jsonl"
PURPOSE_HEADER = "x-aletheia-purpose"
MAX_HEADER_BYTES = 64 * 1024
BUFFER = 64 * 1024

# Hop-by-hop headers that must not be forwarded.
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class ProxyError(Exception):
    """A malformed or unsupported client request."""


def parse_request_line(line: str) -> tuple[str, str, str]:
    """Split ``METHOD TARGET VERSION`` into its three parts."""
    parts = line.split()
    if len(parts) != 3:
        raise ProxyError(f"malformed request line: {line!r}")
    method, target, version = parts
    if not version.startswith("HTTP/"):
        raise ProxyError(f"unsupported HTTP version: {version!r}")
    return method.upper(), target, version


def host_port_from_target(method: str, target: str) -> tuple[str, int, str]:
    """Resolve ``(host, port, path)`` for a CONNECT or absolute-form target."""
    if method == "CONNECT":
        host, _, raw_port = target.partition(":")
        if not host:
            raise ProxyError(f"malformed CONNECT target: {target!r}")
        try:
            port = int(raw_port) if raw_port else 443
        except ValueError as exc:
            raise ProxyError(f"malformed CONNECT port: {target!r}") from exc
        return host, port, ""
    split = urlsplit(target)
    if not split.scheme or not split.hostname:
        raise ProxyError("forward proxy requires an absolute-form target (http://host/path)")
    port = split.port or (443 if split.scheme == "https" else 80)
    path = split.path or "/"
    if split.query:
        path += "?" + split.query
    return split.hostname, port, path


def make_log_record(
    *,
    adapter: str,
    method: str,
    host: str,
    path: str,
    status: int,
    nbytes: int,
    purpose_id: str,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    """Build one request-log record in the schema the reader validates."""
    return {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "adapter": adapter,
        "method": method,
        "host": host or "",
        "path": path or "",
        "status": int(status),
        "bytes": int(nbytes),
        "purpose_id": purpose_id or "unspecified",
        "request_id": request_id or uuid4().hex,
    }


class TokenBucket:
    """A token bucket with a monotonic clock (one per adapter for the process)."""

    def __init__(self, rate: float, capacity: float) -> None:
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate and capacity must be > 0")
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.updated_at = time.monotonic()

    def allow(self, cost: float = 1.0, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else float(now)
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.updated_at = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


def _headers_to_dict(header_lines: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in header_lines:
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    return headers


def _forward_headers(header_lines: list[str]) -> list[str]:
    kept = []
    for line in header_lines:
        key = line.partition(":")[0].strip().lower()
        if key in _HOP_BY_HOP:
            continue
        kept.append(line)
    return kept


async def _read_head(reader: asyncio.StreamReader) -> tuple[str, list[str]]:
    raw_line = await reader.readline()
    if not raw_line:
        raise ProxyError("client closed before sending a request line")
    if len(raw_line) > MAX_HEADER_BYTES:
        raise ProxyError("request line too long")
    request_line = raw_line.decode("latin-1").rstrip("\r\n")
    header_lines: list[str] = []
    total = len(raw_line)
    while True:
        raw = await reader.readline()
        if not raw:
            break
        total += len(raw)
        if total > MAX_HEADER_BYTES:
            raise ProxyError("request headers too large")
        if raw in (b"\r\n", b"\n"):
            break
        header_lines.append(raw.decode("latin-1").rstrip("\r\n"))
    return request_line, header_lines


async def _write_simple(writer: asyncio.StreamWriter, status: int, message: str) -> None:
    body = message.encode("utf-8") + b"\n"
    writer.write(
        f"HTTP/1.1 {status} {message}\r\n".encode("latin-1")
        + b"Content-Type: text/plain; charset=utf-8\r\n"
        + f"Content-Length: {len(body)}\r\n".encode("latin-1")
        + b"Connection: close\r\n\r\n"
        + body
    )
    await writer.drain()


def _status_from_line(line: str) -> int:
    parts = line.split(None, 2)
    if len(parts) < 2:
        return 0
    try:
        return int(parts[1])
    except ValueError:
        return 0


class ForwardProxy:
    """The proxy state: config, per-adapter buckets and the request log."""

    def __init__(self, config: dict) -> None:
        self.adapter = config["adapter"]
        self.log_path = Path(config["log_path"])
        self.kill_switch = config["kill_switch"]
        self.rate = config["rate"]
        self.capacity = config["capacity"]
        self._buckets: dict[str, TokenBucket] = {}
        self._log_lock = asyncio.Lock()

    def allow(self, adapter: str) -> bool:
        bucket = self._buckets.get(adapter)
        if bucket is None:
            bucket = TokenBucket(self.rate, self.capacity)
            self._buckets[adapter] = bucket
        return bucket.allow()

    async def log(self, record: dict) -> None:
        async with self._log_lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await self._handle(reader, writer)
        except (ProxyError, asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            try:
                writer.close()
            except OSError:
                pass

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line, header_lines = await _read_head(reader)
        method, target, _ = parse_request_line(request_line)
        headers = _headers_to_dict(header_lines)
        adapter = self.adapter
        purpose_id = headers.get(PURPOSE_HEADER, "unspecified")
        request_id = uuid4().hex

        try:
            host, port, path = host_port_from_target(method, target)
        except ProxyError:
            host, port, path = target, 0, ""

        if self.kill_switch:
            await self.log(make_log_record(adapter=adapter, method=method, host=host, path=path,
                                           status=403, nbytes=0, purpose_id=purpose_id,
                                           request_id=request_id))
            await _write_simple(writer, 403, "kill switch engaged")
            return
        if not self.allow(adapter):
            await self.log(make_log_record(adapter=adapter, method=method, host=host, path=path,
                                           status=429, nbytes=0, purpose_id=purpose_id,
                                           request_id=request_id))
            await _write_simple(writer, 429, "rate limited")
            return

        try:
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
        except OSError:
            await self.log(make_log_record(adapter=adapter, method=method, host=host, path=path,
                                           status=502, nbytes=0, purpose_id=purpose_id,
                                           request_id=request_id))
            await _write_simple(writer, 502, "upstream connect failed")
            return

        try:
            if method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                nbytes = await self._tunnel(reader, writer, remote_reader, remote_writer)
                status = 200
            else:
                status, nbytes = await self._forward_http(
                    reader, writer, remote_reader, remote_writer,
                    method, path, header_lines, headers,
                )
        finally:
            remote_writer.close()

        await self.log(make_log_record(adapter=adapter, method=method, host=host, path=path,
                                       status=status, nbytes=nbytes, purpose_id=purpose_id,
                                       request_id=request_id))

    async def _tunnel(self, reader, writer, remote_reader, remote_writer) -> int:
        return await _pump(remote_reader, writer)

    async def _forward_http(self, reader, writer, remote_reader, remote_writer,
                            method, path, header_lines, headers) -> tuple[int, int]:
        request_head = f"{method} {path} HTTP/1.1\r\n" + "".join(
            line + "\r\n" for line in _forward_headers(header_lines)
        ) + "\r\n"
        remote_writer.write(request_head.encode("latin-1"))

        body_length = 0
        try:
            body_length = int(headers.get("content-length", "0"))
        except ValueError:
            body_length = 0
        if body_length > 0:
            body = await reader.readexactly(body_length)
            remote_writer.write(body)
        await remote_writer.drain()

        status_line = (await remote_reader.readline()).decode("latin-1")
        status = _status_from_line(status_line)
        writer.write(status_line.encode("latin-1"))
        while True:
            header_line = await remote_reader.readline()
            if not header_line or header_line in (b"\r\n", b"\n"):
                writer.write(b"\r\n")
                break
            writer.write(header_line)
        await writer.drain()

        nbytes = await _pump(remote_reader, writer)
        return status, nbytes


async def _pump(source: asyncio.StreamReader, sink: asyncio.StreamWriter) -> int:
    """Copy bytes from source to sink until EOF; return the byte count."""
    total = 0
    while True:
        data = await source.read(BUFFER)
        if not data:
            break
        total += len(data)
        sink.write(data)
        await sink.drain()
    try:
        sink.write_eof()
    except (OSError, RuntimeError):
        pass
    return total


def config_from_env(environ: dict | None = None) -> dict:
    env = os.environ if environ is None else environ
    return {
        "adapter": env.get("ALETHEIA_ADAPTER", "unknown"),
        "log_path": env.get("ALETHEIA_EGRESS_LOG", DEFAULT_LOG),
        "port": int(env.get("ALETHEIA_EGRESS_PORT", DEFAULT_PORT)),
        "kill_switch": str(env.get("ALETHEIA_EGRESS_KILL_SWITCH", "")).strip().lower()
        in {"1", "true", "yes", "on"},
        "rate": float(env.get("ALETHEIA_EGRESS_RATE", "1")),
        "capacity": float(env.get("ALETHEIA_EGRESS_BURST", "1")),
    }


async def serve(config: dict) -> None:
    proxy = ForwardProxy(config)
    server = await asyncio.start_server(proxy.handle, host="0.0.0.0", port=config["port"])
    print(
        json.dumps(
            {"health": "ok", "adapter": config["adapter"], "port": config["port"],
             "kill_switch": config["kill_switch"], "log_path": config["log_path"]},
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    async with server:
        await server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--health"]:
        # No socket is opened; stdout must stay exactly "ok".
        print("ok")
        return 0
    config = config_from_env()
    try:
        asyncio.run(serve(config))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
