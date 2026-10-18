"""Tests for the parent-linked cascade trail (P17.8)."""

from __future__ import annotations

import pytest

from aletheia.cascade.trail import TrailError, TrailHop, build_trail, trail_digest
from aletheia.core.models import SeedType


def _hop(
    hop_id: str,
    *,
    parent: str | None = None,
    seed_type: SeedType = SeedType.EMAIL,
    value: str = "a@example.com",
    depth: int = 1,
    outcome: str = "expanded",
    claims: int = 1,
    reason: str = "",
) -> TrailHop:
    return TrailHop(
        hop_id=hop_id,
        parent_hop_id=parent,
        seed_type=seed_type,
        seed_value=value,
        depth=depth,
        outcome=outcome,
        claims_found=claims,
        reason=reason,
    )


def test_build_trail_orders_and_links():
    hops = [
        _hop("b", parent="a", depth=2, seed_type=SeedType.USERNAME, value="alice", outcome="skipped", reason="no coverage"),
        _hop("a"),
        _hop("c", depth=1, outcome="blocked", claims=0, reason="gate: third-party firewall"),
    ]
    trail = build_trail(hops, run_id="r1", case_id="c1")
    assert [hop["hop_id"] for hop in trail["hops"]] == ["a", "c", "b"]
    assert trail["hops"][2]["parent_hop_id"] == "a"
    assert trail["hops"][0]["parent_hop_id"] is None
    assert trail["run_id"] == "r1"
    assert trail["case_id"] == "c1"


def test_digest_is_stable_and_run_independent():
    hops = [_hop("a"), _hop("b", parent="a", depth=2, value="b@example.com")]
    first = build_trail(hops, run_id="r1")
    second = build_trail(hops, run_id="r2")
    assert trail_digest(first) == trail_digest(second)
    smaller = build_trail([_hop("a")], run_id="r1")
    assert trail_digest(smaller) != trail_digest(first)


def test_validation_errors():
    with pytest.raises(TrailError):
        build_trail([_hop("a"), _hop("a")])
    with pytest.raises(TrailError):
        build_trail([_hop("a", parent="missing")])
    with pytest.raises(TrailError):
        build_trail([_hop("a", outcome="merged")])
    with pytest.raises(TrailError):
        build_trail([_hop("a", outcome="refused")])
    with pytest.raises(TrailError):
        build_trail([_hop("a", depth=0)])
    with pytest.raises(TrailError):
        build_trail([_hop("a", claims=-1)])
    with pytest.raises(TrailError):
        build_trail([TrailHop(hop_id="", seed_type=SeedType.EMAIL, seed_value="x", depth=1, outcome="expanded")])
    with pytest.raises(TrailError):
        build_trail([TrailHop(hop_id="a", seed_type=SeedType.EMAIL, seed_value="", depth=1, outcome="expanded")])


def test_cycle_detected():
    with pytest.raises(TrailError):
        build_trail([_hop("a", parent="b"), _hop("b", parent="a")])


def test_empty_trail_is_allowed():
    trail = build_trail([])
    assert trail["hops"] == []
    assert trail_digest(trail) == trail_digest(build_trail([], run_id="other"))
