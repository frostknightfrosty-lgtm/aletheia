"""Tests for the blind-spot registry (P17.7)."""

from __future__ import annotations

import pytest

from aletheia.core.blind_spots import KNOWN_LIMITS, BlindSpotRegistry, BlindSpotStore


def test_curated_limits_are_cited():
    for source, limits in KNOWN_LIMITS.items():
        assert limits, source
        for limitation in limits:
            markers = ("design section", "docs/", "GATES.md")
            assert any(marker in limitation for marker in markers), limitation


def test_registry_merges_curated_and_observed(tmp_path):
    store = BlindSpotStore(tmp_path / "blind_spots.jsonl")
    registry = BlindSpotRegistry(store)
    registry.record("instaloader", "observed: rate-limited during a run", run_id="r1")
    limits = registry.limits_for("instaloader")
    assert limits[0] == KNOWN_LIMITS["instaloader"][0]
    assert limits[-1] == "observed: rate-limited during a run"
    assert "instaloader" in registry.sources()


def test_store_persists_and_filters(tmp_path):
    store = BlindSpotStore(tmp_path / "blind_spots.jsonl")
    store.record("a", "limit a")
    store.record("b", "limit b")
    reopened = BlindSpotStore(tmp_path / "blind_spots.jsonl")
    assert [entry.source for entry in reopened.all()] == ["a", "b"]
    assert [entry.limitation for entry in reopened.limits_for("a")] == ["limit a"]
    assert reopened.limits_for("missing") == ()


def test_registry_without_store_reads_curated_only():
    registry = BlindSpotRegistry()
    assert registry.limits_for("hibp") == KNOWN_LIMITS["hibp"]
    assert registry.limits_for("unknown-source") == ()
    assert registry.sources() == tuple(sorted(KNOWN_LIMITS))
    with pytest.raises(ValueError):
        registry.record("x", "y")


def test_store_validation(tmp_path):
    store = BlindSpotStore(tmp_path / "blind_spots.jsonl")
    with pytest.raises(ValueError):
        store.record("", "limit")
    with pytest.raises(ValueError):
        store.record("a", "")
