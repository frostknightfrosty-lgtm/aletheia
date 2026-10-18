"""Cross-run source cache with per-source TTLs (P17.7).

Design of record: ``docs/PIVOT_CASCADE.md`` section 9 — "per-source TTL
(profile existence ~30 days, DNS ~7, configuration), cache hits marked in
the trail (no egress); ``--no-cache`` for fresh sweeps; deterministic
replays use the cache only". Section 17's resolution adopts 30d profiles /
7d DNS; ``configuration`` has no design number and is provisionally 7d
(reviewable constant).

Storage: SQLite at the path given (``<data_root>/cache.sqlite3`` by
convention), one row per ``(source, key)``. ``payload`` must be
JSON-serializable. The cache is local state under the data root and is never
committed.

Freshness semantics match the scheduler (``cascade.scheduler.freshness_factor``):
0.0 inside the TTL — the cache answers, so re-asking has no egress value —
ramping to 1.0 over one further TTL. A missing entry reports 1.0 (no cache
coverage: a fresh ask is worth full value).

Honest limits: v1 has no size cap or background eviction; ``evict_expired``
and the purge helpers are explicit. Entries are derived data trusted exactly
as written, never evidence.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aletheia.core.models import utc_now

__all__ = ["DEFAULT_TTL_CLASS", "TTL_CLASSES", "CacheEntry", "SourceCache"]

TTL_CLASSES: dict[str, float] = {
    "profile": 30 * 86400.0,
    "dns": 7 * 86400.0,
    "configuration": 7 * 86400.0,
}

DEFAULT_TTL_CLASS = "profile"


@dataclass(frozen=True)
class CacheEntry:
    """One cached observation with its TTL class materialized as seconds."""

    source: str
    key: str
    payload: Any
    recorded_at: datetime
    ttl_seconds: float

    def age_seconds(self, now: datetime | None = None) -> float:
        return max(0.0, ((now or utc_now()) - self.recorded_at).total_seconds())

    def is_fresh(self, now: datetime | None = None) -> bool:
        """True while the entry is inside its TTL (the cache answers)."""
        return self.age_seconds(now) < self.ttl_seconds

    def freshness(self, now: datetime | None = None) -> float:
        """Scheduler-parity freshness: 0.0 inside TTL, ramping to 1.0."""
        age = self.age_seconds(now)
        if age < self.ttl_seconds:
            return 0.0
        return min(1.0, (age - self.ttl_seconds) / self.ttl_seconds)


class SourceCache:
    """SQLite-backed cross-run cache keyed by ``(source, key)``."""

    def __init__(self, db_path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or utc_now
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS source_cache (
                    source TEXT NOT NULL,
                    key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    ttl_seconds REAL NOT NULL,
                    PRIMARY KEY (source, key)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    # -- writing --------------------------------------------------------------

    def put(
        self,
        source: str,
        key: str,
        payload: Any,
        *,
        ttl_class: str = DEFAULT_TTL_CLASS,
        ttl_seconds: float | None = None,
    ) -> CacheEntry:
        """Store or replace one entry; the TTL is explicit, never guessed."""
        if not source or not key:
            raise ValueError("cache source and key must be non-empty")
        try:
            payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("cache payload must be JSON-serializable") from exc
        if ttl_seconds is None:
            if ttl_class not in TTL_CLASSES:
                raise ValueError(
                    f"unknown ttl_class {ttl_class!r}; known: {', '.join(sorted(TTL_CLASSES))}"
                )
            ttl_seconds = TTL_CLASSES[ttl_class]
        if ttl_seconds <= 0.0:
            raise ValueError("ttl_seconds must be > 0")
        recorded_at = self._clock()
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO source_cache(source,key,payload_json,recorded_at,ttl_seconds) VALUES(?,?,?,?,?)",
                (source, key, payload_json, recorded_at.isoformat(), float(ttl_seconds)),
            )
        return CacheEntry(
            source=source,
            key=key,
            payload=json.loads(payload_json),
            recorded_at=recorded_at,
            ttl_seconds=float(ttl_seconds),
        )

    # -- reading --------------------------------------------------------------

    def get(self, source: str, key: str) -> CacheEntry | None:
        """The stored entry, fresh or not — freshness is visible on the entry."""
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM source_cache WHERE source = ? AND key = ?", (source, key)
            ).fetchone()
        if row is None:
            return None
        return CacheEntry(
            source=row["source"],
            key=row["key"],
            payload=json.loads(row["payload_json"]),
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            ttl_seconds=float(row["ttl_seconds"]),
        )

    def is_fresh(self, source: str, key: str, *, now: datetime | None = None) -> bool:
        entry = self.get(source, key)
        if entry is None:
            return False
        return entry.is_fresh(now or self._clock())

    def freshness(self, source: str, key: str, *, now: datetime | None = None) -> float:
        """0.0 while fresh (the cache answers), 1.0 when uncovered or stale."""
        entry = self.get(source, key)
        if entry is None:
            return 1.0
        return entry.freshness(now or self._clock())

    # -- maintenance ----------------------------------------------------------

    def evict_expired(self, *, now: datetime | None = None) -> int:
        now = now or self._clock()
        with self._connect() as con:
            rows = con.execute("SELECT source, key, recorded_at, ttl_seconds FROM source_cache").fetchall()
            expired = [
                (row["source"], row["key"])
                for row in rows
                if (now - datetime.fromisoformat(row["recorded_at"])).total_seconds()
                >= float(row["ttl_seconds"])
            ]
            for source, key in expired:
                con.execute("DELETE FROM source_cache WHERE source = ? AND key = ?", (source, key))
        return len(expired)

    def purge_source(self, source: str) -> int:
        with self._connect() as con:
            cursor = con.execute("DELETE FROM source_cache WHERE source = ?", (source,))
        return int(cursor.rowcount)

    def purge_all(self) -> int:
        with self._connect() as con:
            cursor = con.execute("DELETE FROM source_cache")
        return int(cursor.rowcount)

    def stats(self) -> dict[str, int]:
        with self._connect() as con:
            total = con.execute("SELECT COUNT(*) AS n FROM source_cache").fetchone()["n"]
            sources = con.execute("SELECT COUNT(DISTINCT source) AS n FROM source_cache").fetchone()["n"]
        return {"entries": int(total), "sources": int(sources)}
