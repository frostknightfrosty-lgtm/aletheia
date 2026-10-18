"""Tests for the confirmed-merge equality graph (P17.5)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from aletheia.cascade.merge_graph import MergeGraph
from aletheia.core.models import ClusterDecision, IdentityTier


def _decision(
    entity_ids: list[str],
    *,
    tier: IdentityTier = IdentityTier.CONFIRMED,
    accepted: bool = True,
    score: float | None = 4.0,
    reason: str = "test merge",
) -> ClusterDecision:
    return ClusterDecision(
        entity_ids=entity_ids, tier=tier, accepted=accepted, score=score, reason=reason
    )


def test_union_find_is_transitive_and_deterministic():
    graph = MergeGraph()
    a, b, c = (str(uuid4()) for _ in range(3))
    graph.merge(a, b, score=5.0)
    graph.merge(b, c, score=2.0)
    assert graph.component(a) == graph.component(c) == frozenset({a, b, c})
    assert graph.find(a) == graph.find(c)
    assert len(graph.groups()) == 1
    assert len(graph.links()) == 2


def test_merge_rejects_self_duplicate_and_nonfinite():
    graph = MergeGraph()
    a, b, c = (str(uuid4()) for _ in range(3))
    with pytest.raises(ValueError):
        graph.merge(a, a, score=1.0)
    graph.merge(a, b, score=1.0)
    with pytest.raises(ValueError):
        graph.merge(b, a, score=1.0)
    with pytest.raises(ValueError):
        graph.merge(a, c, score=float("nan"))


def test_attempt_merge_requires_accepted_confirmed_scored():
    graph = MergeGraph()
    ids = [str(uuid4()), str(uuid4())]
    ok, reason = graph.attempt_merge(_decision(ids, accepted=False))
    assert ok is False and "not accepted" in reason
    ok, reason = graph.attempt_merge(_decision(ids, tier=IdentityTier.PROBABLE))
    assert ok is False and "confirmed" in reason
    ok, reason = graph.attempt_merge(_decision(ids, score=None))
    assert ok is False and "score" in reason
    assert graph.groups() == []
    decision = _decision(ids)
    ok, reason = graph.attempt_merge(decision)
    assert ok is True and reason == ""
    assert len(graph.groups()) == 1
    assert graph.links()[0].decision_id == decision.decision_id
    ok, reason = graph.attempt_merge(_decision(ids))
    assert ok is False and "already merged" in reason
    assert len(graph.links()) == 1


def test_attempt_merge_chains_all_entities_and_rejects_repeats():
    graph = MergeGraph()
    ids = [str(uuid4()) for _ in range(3)]
    ok, reason = graph.attempt_merge(_decision(ids, score=4.2))
    assert ok is True and reason == ""
    assert len(graph.groups()) == 1
    assert len(graph.links()) == 2
    repeated = str(uuid4())
    ok, reason = graph.attempt_merge(_decision([repeated, repeated]))
    assert ok is False and "repeats" in reason


def test_conflict_reopens_chain_and_demotes_weakest():
    graph = MergeGraph()
    graph.merge("a", "b", score=5.0)
    graph.merge("b", "c", score=2.0)
    graph.merge("c", "d", score=5.0)
    record = graph.conflict("a", "d", reason="conflicting vin")
    assert record.chain_reopened is True
    assert record.demoted is not None
    assert frozenset({record.demoted.left, record.demoted.right}) == frozenset({"b", "c"})
    assert record.demoted.score == 2.0
    assert graph.demoted_links() == (record.demoted,)
    assert len(graph.links()) == 2
    remaining = [set(members) for members in graph.groups()]
    assert sorted(remaining, key=sorted) == [{"a", "b"}, {"c", "d"}]
    assert graph.conflicts() == (record,)


def test_conflict_across_components_is_recorded_without_reopen():
    graph = MergeGraph()
    record = graph.conflict("x", "y", reason="conflicting names")
    assert record.chain_reopened is False
    assert record.demoted is None
    assert graph.demoted_links() == ()
    assert [set(members) for members in graph.groups()] == [{"x"}, {"y"}]
    assert graph.conflicts() == (record,)


def test_weakest_link_tie_is_deterministic():
    graph = MergeGraph()
    graph.merge("a", "b", score=3.0)
    graph.merge("b", "c", score=3.0)
    record = graph.conflict("a", "c", reason="conflicting names")
    assert record.demoted is not None
    assert frozenset({record.demoted.left, record.demoted.right}) == frozenset({"a", "b"})
    remaining = [set(members) for members in graph.groups()]
    assert sorted(remaining, key=sorted) == [{"a"}, {"b", "c"}]


def test_demoted_pair_can_be_merged_again_with_new_evidence():
    graph = MergeGraph()
    graph.merge("a", "b", score=1.0)
    graph.conflict("a", "b", reason="conflicting demographics")
    assert [set(members) for members in graph.groups()] == [{"a"}, {"b"}]
    relinked = graph.merge("a", "b", score=9.0, reason="re-reviewed")
    assert relinked.score == 9.0
    assert len(graph.groups()) == 1
