"""Minimal DSN parsing shared by the networked storage backends.

Kept dependency-free so the backends can be configured from environment
variables of the form ``scheme://user:password@host:port/database`` (or the
scheme-specific variants documented per backend) without importing a driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit


@dataclass(frozen=True)
class Dsn:
    scheme: str
    host: str
    port: int | None
    username: str | None
    password: str | None
    database: str
    params: dict[str, str]

    @property
    def hostport(self) -> tuple[str, int | None]:
        return self.host, self.port


def parse_dsn(url: str, *, default_port: int | None = None) -> Dsn:
    parts = urlsplit(url)
    if not parts.scheme:
        raise ValueError(f"DSN has no scheme: {url!r}")
    database = unquote(parts.path.lstrip("/"))
    return Dsn(
        scheme=parts.scheme,
        host=parts.hostname or "localhost",
        port=parts.port or default_port,
        username=unquote(parts.username) if parts.username else None,
        password=unquote(parts.password) if parts.password else None,
        database=database,
        params={k: v[-1] for k, v in parse_qs(parts.query).items()},
    )
