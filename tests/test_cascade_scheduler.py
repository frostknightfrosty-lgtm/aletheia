"""Tests for the VOI scheduler, budgets, stops, and resume (P17.6)."""

from __future__ import annotations

import pytest

from aletheia.cascade.ledger import DecisionLedger
from aletheia.cascade.scheduler import (
    DEFAULT_YIELD,
    CascadeScheduler,
    SchedulerPolicy,
    StopReason,
    freshness_factor,
    voi_score,
)
from aletheia.cascade.scoring import EvidenceClass
from aletheia.core.models import EntityType, IdentityTier, PivotCandidate, Seed, SeedType


def _candidate(seed_type: SeedType, value: str, *, gate: IdentityTier = IdentityTier.CONFIRMED) -> PivotCandidate:
    return PivotCandidate(
        claim_entity_type=EntityType.EMAIL,
        claim_value="seed@example.com",
        seed=Seed(type=seed_type, value=value),
        gate=gate,
        reason="test pivot",
    )


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_voi_formula_and_validation():
    assert voi_score(prior_probability=0.5) == pytest.approx(0.5 * DEFAULT_YIELD * 0.5)
    assert voi_score(prior_probability=0.5, depth=2) == pytest.approx(0.25 * 0.6)
    # Cost is clamped so a zero-cost replay cannot divide by zero.
    assert voi_score(prior_probability=0.5, cost=0.0) == pytest.approx(0.25 / 0.1)
    with pytest.raises(ValueError):
        voi_score(prior_probability=1.5)
    with pytest.raises(ValueError):
        voi_score(prior_probability=0.5, freshness=1.5)
    with pytest.raises(ValueError):
        voi_score(prior_probability=0.5, depth=0)
    with pytest.raises(ValueError):
        voi_score(prior_probability=0.5, cost=-1.0)


def test_freshness_factor_ramp():
    assert freshness_factor(age_seconds=5.0, ttl_seconds=30.0) == 0.0
    assert freshness_factor(age_seconds=30.0, ttl_seconds=30.0) == 0.0
    assert freshness_factor(age_seconds=45.0, ttl_seconds=30.0) == pytest.approx(0.5)
    assert freshness_factor(age_seconds=90.0, ttl_seconds=30.0) == 1.0
    assert freshness_factor(age_seconds=5.0, ttl_seconds=0.0) == 1.0
    with pytest.raises(ValueError):
        freshness_factor(age_seconds=-1.0, ttl_seconds=30.0)


def test_pop_order_is_priority_then_insertion_sequence():
    scheduler = CascadeScheduler()
    first = scheduler.push(_candidate(SeedType.EMAIL, "a@example.com"), prior_probability=0.8)
    low = scheduler.push(_candidate(SeedType.EMAIL, "b@example.com"), prior_probability=0.2)
    second = scheduler.push(_candidate(SeedType.USERNAME, "alice"), prior_probability=0.8)
    assert first is not None and low is not None and second is not None
    popped = [scheduler.pop().candidate.seed.value for _ in range(3)]
    assert popped == ["a@example.com", "alice", "b@example.com"]


def test_push_refusals_are_recorded_not_silent():
    ledger = DecisionLedger()
    scheduler = CascadeScheduler(ledger=ledger)
    candidate = _candidate(SeedType.EMAIL, "fresh@example.com")
    assert scheduler.push(candidate, prior_probability=0.5, freshness=0.0) is None
    # A fresh refusal does not poison the dedup key: a stale re-push works.
    assert scheduler.push(candidate, prior_probability=0.5) is not None
    assert scheduler.push(_candidate(SeedType.EMAIL, "fresh@example.com"), prior_probability=0.5) is None
    assert scheduler.push(_candidate(SeedType.EMAIL, "deep@example.com"), prior_probability=0.5, depth=6) is None
    refusals = [entry for entry in ledger.replay(kinds=["pivot_refused"])]
    assert [entry.payload["reason"] for entry in refusals] == [
        "fresh_cache",
        "duplicate",
        "beyond_hard_depth",
    ]
    assert len([entry for entry in ledger.replay(kinds=["pivot_proposed"])]) == 1


def test_dedup_is_per_seed_type_and_value():
    scheduler = CascadeScheduler()
    assert scheduler.push(_candidate(SeedType.EMAIL, "x"), prior_probability=0.5) is not None
    assert scheduler.push(_candidate(SeedType.USERNAME, "x"), prior_probability=0.5) is not None
    assert scheduler.push(_candidate(SeedType.EMAIL, "x"), prior_probability=0.5) is None
    assert scheduler.frontier_size == 2


def test_depth_policy_escalation_requires_owner_mode_and_hard_evidence():
    owner = CascadeScheduler(policy=SchedulerPolicy(owner_mode=True))
    deep = owner.push(_candidate(SeedType.DOMAIN, "alice.example"), prior_probability=1.0, depth=4)
    assert deep is not None
    assert owner.pop() is None
    assert owner.should_stop() is StopReason.DEPTH
    assert owner.frontier_size == 1  # all-depth-blocked entries stay for a later escalation
    owner.note_evidence(EvidenceClass.HARD)
    assert owner.effective_depth_limit() == 5
    assert owner.pop() is not None

    non_owner = CascadeScheduler(policy=SchedulerPolicy(owner_mode=False))
    non_owner.push(_candidate(SeedType.DOMAIN, "bob.example"), prior_probability=1.0, depth=4)
    non_owner.note_evidence(EvidenceClass.HARD)
    assert non_owner.effective_depth_limit() == 3
    assert non_owner.pop() is None


def test_time_pressure_de_escalates_depth_and_time_budget_stops():
    clock = _Clock()
    policy = SchedulerPolicy(owner_mode=True, time_budget_seconds=100.0)
    scheduler = CascadeScheduler(policy, clock=clock)
    scheduler.note_evidence(EvidenceClass.HARD)
    assert scheduler.effective_depth_limit() == 5
    clock.now = 75.0
    assert scheduler.time_pressure() is True
    assert scheduler.effective_depth_limit() == 4
    clock.now = 100.0
    assert scheduler.should_stop() is StopReason.TIME
    assert scheduler.pop() is None


def test_per_type_caps_refuse_only_the_capped_type():
    policy = SchedulerPolicy(per_type_caps={SeedType.EMAIL: 2})
    ledger = DecisionLedger()
    scheduler = CascadeScheduler(policy, ledger=ledger)
    for value in ("e1@example.com", "e2@example.com", "e3@example.com"):
        scheduler.push(_candidate(SeedType.EMAIL, value), prior_probability=1.0)
    scheduler.push(_candidate(SeedType.USERNAME, "alice"), prior_probability=0.4)
    assert scheduler.pop() is not None
    assert scheduler.pop() is not None
    # Third pop scans past the capped email and grants the username instead.
    third = scheduler.pop()
    assert third is not None and third.candidate.seed.type is SeedType.USERNAME
    assert scheduler.used_for(SeedType.EMAIL) == 2
    assert scheduler.expansions == 3
    refusals = [entry for entry in ledger.replay(kinds=["pivot_refused"])]
    assert [entry.payload["reason"] for entry in refusals] == ["budget"]
    # The capped refusal was recorded and dropped; a newly proposed email
    # makes the all-capped condition observable as the budget stop.
    scheduler.push(_candidate(SeedType.EMAIL, "e4@example.com"), prior_probability=1.0)
    assert scheduler.should_stop() is StopReason.BUDGET
    assert scheduler.pop() is None


def test_max_expansions_budget_stop():
    scheduler = CascadeScheduler(policy=SchedulerPolicy(max_expansions=2))
    for index in range(3):
        scheduler.push(_candidate(SeedType.USERNAME, f"user{index}"), prior_probability=1.0)
    assert scheduler.pop() is not None
    assert scheduler.pop() is not None
    assert scheduler.should_stop() is StopReason.BUDGET
    assert scheduler.pop() is None
    assert scheduler.expansions == 2


def test_saturation_stops_even_with_pending_entries():
    scheduler = CascadeScheduler()
    scheduler.push(_candidate(SeedType.EMAIL, "a@example.com"), prior_probability=1.0)
    scheduler.note_pass(added_above_floor=2)
    assert scheduler.should_stop() is None
    scheduler.note_pass(added_above_floor=0)
    assert scheduler.saturated is True
    assert scheduler.should_stop() is StopReason.SATURATED
    assert scheduler.pop() is None


def test_diminishing_returns_below_min_voi():
    scheduler = CascadeScheduler()
    scheduler.push(_candidate(SeedType.EMAIL, "a@example.com"), prior_probability=0.01)
    assert scheduler.should_stop() is StopReason.DIMINISHING_RETURNS
    assert scheduler.pop() is None
    assert scheduler.frontier_size == 1
    assert scheduler.should_stop() is StopReason.DIMINISHING_RETURNS


def test_empty_frontier_is_not_a_stop():
    scheduler = CascadeScheduler()
    assert scheduler.should_stop() is None
    assert scheduler.pop() is None
    assert scheduler.should_stop() is None


def test_user_stop_latches_once():
    ledger = DecisionLedger()
    scheduler = CascadeScheduler(ledger=ledger)
    scheduler.push(_candidate(SeedType.EMAIL, "a@example.com"), prior_probability=1.0)
    assert scheduler.stop(StopReason.USER_STOP, note="operator") is True
    assert scheduler.stop(StopReason.BUDGET) is False
    assert scheduler.stop_reason is StopReason.USER_STOP
    assert scheduler.stop_note == "operator"
    assert scheduler.should_stop() is StopReason.USER_STOP
    assert scheduler.pop() is None
    stops = [entry for entry in ledger.replay(kinds=["stop"])]
    assert len(stops) == 1
    assert stops[0].payload["reason"] == "user_stop"


def test_checkpoint_round_trip_preserves_order_and_budget():
    ledger = DecisionLedger()
    scheduler = CascadeScheduler(ledger=ledger, rng_seed=42)
    for index, value in enumerate(("a@example.com", "b@example.com", "c@example.com")):
        scheduler.push(_candidate(SeedType.EMAIL, value), prior_probability=0.4 + index * 0.1)
    scheduler.push(_candidate(SeedType.USERNAME, "alice"), prior_probability=0.35)
    scheduler.pop()
    scheduler.note_pass(added_above_floor=3)

    restored = CascadeScheduler.from_checkpoint(
        scheduler.checkpoint(), ledger=DecisionLedger()
    )
    assert restored.rng_seed == 42
    assert restored.expansions == scheduler.expansions == 1
    assert restored.passes == scheduler.passes == 1
    assert [entry.candidate.seed.value for entry in restored.pending()] == [
        entry.candidate.seed.value for entry in scheduler.pending()
    ]
    assert restored.used_for(SeedType.EMAIL) == 1
    original_order = [scheduler.pop().candidate.seed.value for _ in range(scheduler.frontier_size)]
    restored_order = [restored.pop().candidate.seed.value for _ in range(restored.frontier_size)]
    assert restored_order == original_order


def test_checkpoint_preserves_stop_state_and_rejects_bad_version():
    scheduler = CascadeScheduler()
    scheduler.push(_candidate(SeedType.EMAIL, "a@example.com"), prior_probability=1.0)
    scheduler.stop(StopReason.USER_STOP, note="operator")
    restored = CascadeScheduler.from_checkpoint(scheduler.checkpoint())
    assert restored.stop_reason is StopReason.USER_STOP
    assert restored.stop_note == "operator"
    with pytest.raises(ValueError):
        CascadeScheduler.from_checkpoint({"checkpoint_version": 99})


def test_policy_validation():
    with pytest.raises(ValueError):
        SchedulerPolicy(default_depth=0)
    with pytest.raises(ValueError):
        SchedulerPolicy(default_depth=4, hard_depth=3)
    with pytest.raises(ValueError):
        SchedulerPolicy(min_voi=-0.1)
    with pytest.raises(ValueError):
        SchedulerPolicy(time_budget_seconds=0.0)
    with pytest.raises(ValueError):
        SchedulerPolicy(per_type_caps={SeedType.EMAIL: -1})
    with pytest.raises(ValueError):
        SchedulerPolicy(max_expansions=-1)
