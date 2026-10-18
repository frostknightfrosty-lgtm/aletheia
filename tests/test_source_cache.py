"""Tests for the cross-run source cache (P17.7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aletheia.cascade.scheduler import freshness_factor
from aletheia.core.source_cache import TTL_CLASSES, SourceCache

_FIXED = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)


class _Clock:
    def __init__(self, now: datetime = _FIXED) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_put_get_round_trip(tmp_path):
    cache = SourceCache(tmp_path / "cache.sqlite3")
    entry = cache.put("adapters.github", "alice", {"exists": True, "bio": "b"})
    assert entry.ttl_seconds == TTL_CLASSES["profile"]
    fetched = cache.get("adapters.github", "alice")
    assert fetched is not None
    assert fetched.payload == {"exists": True, "bio": "b"}
    assert cache.get("adapters.github", "missing") is None


def test_put_validation(tmp_path):
    cache = SourceCache(tmp_path / "cache.sqlite3")
    with pytest.raises(ValueError):
        cache.put("s", "k", {}, ttl_class="nope")
    with pytest.raises(ValueError):
        cache.put("s", "k", {}, ttl_seconds=0.0)
    with pytest.raises(ValueError):
        cache.put("", "k", {})
    with pytest.raises(ValueError):
        cache.put("s", "", {})
    with pytest.raises(ValueError):
        cache.put("s", "k", {1, 2})


def test_freshness_semantics_and_scheduler_parity(tmp_path):
    clock = _Clock()
    cache = SourceCache(tmp_path / "cache.sqlite3", clock=clock)
    cache.put("dns_resolver", "alice.example", {"ip": "1.2.3.4"}, ttl_class="dns")
    ttl = TTL_CLASSES["dns"]

    assert cache.is_fresh("dns_resolver", "alice.example") is True
    assert cache.freshness("dns_resolver", "alice.example") == 0.0
    assert cache.is_fresh("dns_resolver", "unknown.example") is False
    assert cache.freshness("dns_resolver", "unknown.example") == 1.0

    clock.now = _FIXED + timedelta(seconds=ttl * 1.5)
    entry = cache.get("dns_resolver", "alice.example")
    assert entry.is_fresh(clock.now) is False
    assert entry.freshness(clock.now) == pytest.approx(0.5)
    # Parity with the scheduler's freshness semantics (the VOI hook).
    assert cache.freshness("dns_resolver", "alice.example") == pytest.approx(
        freshness_factor(entry.age_seconds(clock.now), ttl)
    )

    clock.now = _FIXED + timedelta(seconds=ttl * 2)
    assert cache.freshness("dns_resolver", "alice.example") == 1.0


def test_ttl_override_and_replace(tmp_path):
    clock = _Clock()
    cache = SourceCache(tmp_path / "cache.sqlite3", clock=clock)
    cache.put("s", "k", 1, ttl_seconds=60.0)
    assert cache.get("s", "k").ttl_seconds == 60.0
    cache.put("s", "k", 2, ttl_seconds=60.0)
    assert cache.get("s", "k").payload == 2
    assert cache.stats() == {"entries": 1, "sources": 1}


def test_evict_expired_and_purge(tmp_path):
    clock = _Clock()
    cache = SourceCache(tmp_path / "cache.sqlite3", clock=clock)
    cache.put("a", "k1", {})
    cache.put("b", "k2", {}, ttl_seconds=10.0)
    clock.now = _FIXED + timedelta(seconds=11.0)
    assert cache.evict_expired() == 1
    assert cache.get("b", "k2") is None
    assert cache.get("a", "k1") is not None
    assert cache.purge_source("a") == 1
    cache.put("a", "k3", {})
    assert cache.purge_all() == 1
    assert cache.stats() == {"entries": 0, "sources": 0}


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "cache.sqlite3"
    SourceCache(path).put("s", "k", {"v": 1})
    assert SourceCache(path).get("s", "k").payload == {"v": 1}
