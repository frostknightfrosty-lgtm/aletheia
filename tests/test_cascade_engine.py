"""Cascade engine tests: synthetic worlds, adversarial traps, failure injection.

Design of record: ``docs/PIVOT_CASCADE.md`` section 13. The engine
(``aletheia.cascade.engine``) performs no I/O; these worlds inject observations
directly, so every test here runs in CI with no network and no skips.

Reachability note pinned by these tests: with the P17.3 identical-key blocking,
the evidence table's reachable rows are (a) identical values from independent
origins (HARD/STRONG) and (b) domain-bridged pairs (MEDIUM/WEAK for
domain/host/url claims). Name-class *support* is only reachable for pairs that
share a strong-key block; name conflicts still veto through falsification.
"""

from __future__ import annotations

from aletheia.cascade.claims import claim_from_finding
from aletheia.cascade.engine import CascadeEngine, CascadeResult, Observation
from aletheia.cascade.scheduler import SchedulerPolicy, StopReason
from aletheia.cascade.trail import build_trail, trail_digest
from aletheia.core.models import (
    EntityType,
    Finding,
    Hypothesis,
    IdentityTier,
    Provenance,
    SeedType,
)


def _finding(
    entity_type: EntityType,
    value: str,
    tool: str = "world",
    *,
    attributes: dict[str, object] | None = None,
    confidence: float = 1.0,
) -> Finding:
    return Finding(
        entity_type=entity_type,
        value=value,
        attributes=dict(attributes or {}),
        provenance=Provenance(tool=tool, confidence=confidence, adapter_version="fixture-1"),
    )


def _claim(
    entity_type: EntityType,
    value: str,
    *,
    tool: str = "seed",
    attributes: dict[str, object] | None = None,
):
    return claim_from_finding(_finding(entity_type, value, tool, attributes=attributes))


class World:
    """A pure fixture observer: deterministic answers, no I/O."""

    def __init__(self) -> None:
        self.answers: dict[tuple[SeedType, str], Observation] = {}
        self.calls: list[tuple[SeedType, str]] = []

    def respond(self, seed_type: SeedType, value: str, *findings: Finding) -> "World":
        self.answers[(seed_type, value)] = Observation(findings=tuple(findings))
        return self

    def block(self, seed_type: SeedType, value: str, reason: str) -> "World":
        self.answers[(seed_type, value)] = Observation(blocked_reason=reason)
        return self

    def __call__(self, seed) -> Observation:
        self.calls.append((seed.type, seed.value))
        return self.answers.get((seed.type, seed.value), Observation())


def _assert_decision_invariant(result: CascadeResult) -> None:
    """No merge without both gates: tier confirmed AND ACH H_subject survives."""
    assert len(result.decisions) == len(result.candidates)
    for case in result.candidates:
        expected = (
            case.veto is None
            and case.tier is IdentityTier.CONFIRMED
            and case.ach_surviving is Hypothesis.SUBJECT
        )
        assert case.accepted is expected, case


def _golden_world() -> World:
    return (
        World()
        .respond(
            SeedType.EMAIL,
            "alice@example.com",
            _finding(EntityType.EMAIL, "alice@example.com", "world-mail"),
            _finding(EntityType.USERNAME, "alice", "world-git"),
            _finding(EntityType.URL, "https://github.com/alice", "world-git"),
        )
        .respond(
            SeedType.DOMAIN,
            "example.com",
            _finding(
                EntityType.EMAIL_AUTH_RECORD,
                "v=spf1 include:spf.example.com ~all",
                "world-dns",
            ),
        )
    )


# -- synthetic worlds ---------------------------------------------------------


def test_independent_adapter_confirmation_merges_the_shared_email() -> None:
    world = World().respond(
        SeedType.EMAIL,
        "alice@example.com",
        _finding(EntityType.EMAIL, "alice@example.com", "world-mail"),
    )
    result = CascadeEngine(world).run([_claim(EntityType.EMAIL, "alice@example.com")])

    accepted = [case for case in result.candidates if case.accepted]
    assert len(accepted) == 1
    assert accepted[0].claim.source_adapter == "world-mail"
    assert accepted[0].tier is IdentityTier.CONFIRMED
    assert accepted[0].ach_surviving is Hypothesis.SUBJECT
    assert any(claim.source_adapter == "world-mail" for claim in result.subject_claims)
    assert result.stop_reason is StopReason.SATURATED
    ok, detail = result.ledger.verify()
    assert ok, detail
    merges = list(result.ledger.replay(kinds=["merge"]))
    assert len(merges) == 1
    assert merges[0].payload["accepted"] is True
    _assert_decision_invariant(result)


def test_world_separates_people_and_keeps_shared_platforms_apart() -> None:
    world = (
        World()
        .respond(
            SeedType.EMAIL,
            "alice@example.com",
            _finding(EntityType.EMAIL, "alice@example.com", "world-mail"),
            _finding(EntityType.USERNAME, "alice", "world-git"),
            _finding(EntityType.URL, "https://github.com/alice", "world-git"),
            _finding(EntityType.URL, "https://github.com/bobbuilder", "world-git"),
        )
        .respond(
            SeedType.EMAIL,
            "bob@elsewhere.example",
            _finding(EntityType.EMAIL, "bob@elsewhere.example", "world-mail"),
        )
    )
    result = CascadeEngine(world).run([_claim(EntityType.EMAIL, "alice@example.com")])

    accepted = [case for case in result.candidates if case.accepted]
    assert [case.claim.source_adapter for case in accepted] == ["world-mail"]
    # The colliding handle and both shared-platform URLs stay candidates:
    # a shared host is not identity evidence, and a URL named after Bob is
    # never merged into Alice's cluster.
    assert not any(claim.value.endswith("bobbuilder") for claim in result.subject_claims)
    assert not any(claim.source_adapter == "world-git" for claim in result.subject_claims)
    assert not any(
        case.accepted for case in result.candidates if case.claim.type is EntityType.URL
    )
    _assert_decision_invariant(result)


def test_blocked_observation_is_recorded_and_never_retried() -> None:
    world = World().block(
        SeedType.EMAIL, "alice@example.com", "HTTP 429 from world-mail (rate limited)"
    )
    result = CascadeEngine(world).run([_claim(EntityType.EMAIL, "alice@example.com")])

    blocked = [hop for hop in result.hops if hop.outcome == "blocked"]
    assert len(blocked) == 1
    assert "429" in blocked[0].reason
    assert world.calls.count((SeedType.EMAIL, "alice@example.com")) == 1
    assert not result.candidates
    assert result.stop_reason is StopReason.SATURATED
    build_trail(result.hops)  # a blocked hop with a reason validates


# -- adversarial traps --------------------------------------------------------


def test_adversarial_handle_collision_with_conflicting_national_id_excludes() -> None:
    traps = tuple(
        _finding(
            EntityType.USERNAME,
            "alice",
            f"trap-{suffix}",
            attributes={"national_id": f"X-{suffix}"},
        )
        for suffix in ("111", "222", "333")
    )
    world = World().respond(SeedType.USERNAME, "alice", *traps)
    result = CascadeEngine(world).run(
        [
            _claim(EntityType.USERNAME, "alice"),
            _claim(EntityType.PERSON, "Alice Example", attributes={"national_id": "REAL-001"}),
        ]
    )

    assert len(result.candidates) == 3
    for case in result.candidates:
        assert case.accepted is False
        assert case.tier is IdentityTier.EXCLUDED
        assert case.veto is not None and "national_id" in case.veto
    assert not any(claim.source_adapter.startswith("trap") for claim in result.subject_claims)
    assert len(result.graph.conflicts()) == 3
    # Only the two root pivots were ever expanded; the traps spawned nothing.
    assert result.expansions == 2
    _assert_decision_invariant(result)


def test_adversarial_name_conflict_excludes_before_any_merge() -> None:
    world = World().respond(
        SeedType.USERNAME,
        "alice",
        _finding(EntityType.PERSON, "Bob", "trap-name"),
    )
    result = CascadeEngine(world).run(
        [
            _claim(EntityType.USERNAME, "alice"),
            _claim(EntityType.PERSON, "Alice Smith"),
        ]
    )

    assert len(result.candidates) == 1
    case = result.candidates[0]
    assert case.accepted is False
    assert case.tier is IdentityTier.EXCLUDED
    assert case.veto is not None and "name-class" in case.veto
    assert case.ach_surviving is None
    assert not any(claim.source_adapter == "trap-name" for claim in result.subject_claims)


# -- gates and budgets --------------------------------------------------------


def test_personal_pivots_are_gated_below_confirmed_origin() -> None:
    world = World().respond(
        SeedType.USERNAME,
        "alice",
        _finding(EntityType.USERNAME, "alice", "world-git"),
        _finding(EntityType.EMAIL, "alice@personal.example.com", "world-git"),
    )
    result = CascadeEngine(world).run([_claim(EntityType.USERNAME, "alice")])

    # The handle echo is a single independent STRONG signal: possible, not merged.
    echo = next(case for case in result.candidates if case.claim.type is EntityType.USERNAME)
    assert echo.accepted is False
    assert echo.tier is IdentityTier.POSSIBLE
    email_case = next(case for case in result.candidates if case.claim.type is EntityType.EMAIL)
    assert email_case.accepted is False
    assert email_case.tier is None

    gated = {
        entry.payload["seed_value"]: entry.payload["gate"]
        for entry in result.ledger.replay(kinds=["pivot_gated"])
        if entry.payload["seed_value"]
        in {"alice@personal.example.com", "personal.example.com"}
    }
    assert gated == {"alice@personal.example.com": "confirmed", "personal.example.com": "probable"}
    proposed = {
        entry.payload["seed_value"] for entry in result.ledger.replay(kinds=["pivot_proposed"])
    }
    assert "alice@personal.example.com" not in proposed
    assert "personal.example.com" not in proposed
    assert result.expansions == 1  # only the root handle pivot ever ran


def test_budget_stop_latches_and_records_one_stop_entry() -> None:
    result = CascadeEngine(
        _golden_world(), policy=SchedulerPolicy(max_expansions=1)
    ).run([_claim(EntityType.EMAIL, "alice@example.com")])

    assert result.stop_reason is StopReason.BUDGET
    assert result.expansions == 1
    stops = list(result.ledger.replay(kinds=["stop"]))
    assert len(stops) == 1
    assert stops[0].payload["reason"] == "budget"


def test_pivots_beyond_the_hard_depth_are_refused_and_recorded() -> None:
    result = CascadeEngine(
        _golden_world(), policy=SchedulerPolicy(default_depth=1, hard_depth=1)
    ).run([_claim(EntityType.EMAIL, "alice@example.com")])

    # The confirmed echo pumps its follow-up pivots one level deeper; with the
    # hard depth at one, every one of those is refused and recorded, and the
    # run still saturates honestly with only depth-one expansions.
    refused = [
        entry.payload
        for entry in result.ledger.replay(kinds=["pivot_refused"])
        if entry.payload["reason"] == "beyond_hard_depth"
    ]
    assert refused
    assert {payload["depth"] for payload in refused} == {2}
    assert {hop.depth for hop in result.hops} == {1}
    assert result.expansions == 2
    assert result.stop_reason is StopReason.SATURATED
    ok, detail = result.ledger.verify()
    assert ok, detail


# -- golden run ---------------------------------------------------------------


def test_golden_run_digest_is_deterministic_and_changes_with_the_world() -> None:
    roots = [_claim(EntityType.EMAIL, "alice@example.com")]
    first = CascadeEngine(_golden_world()).run(roots)
    second = CascadeEngine(_golden_world()).run(
        [_claim(EntityType.EMAIL, "alice@example.com")]
    )

    first_trail = build_trail(first.hops)
    second_trail = build_trail(second.hops)
    assert first_trail["hops"] == second_trail["hops"]
    assert trail_digest(first_trail) == trail_digest(second_trail)

    other = CascadeEngine(World()).run([_claim(EntityType.EMAIL, "alice@example.com")])
    assert trail_digest(build_trail(other.hops)) != trail_digest(first_trail)

    kinds = {entry.kind for entry in first.ledger.replay()}
    assert {"pivot_proposed", "pivot_granted", "merge", "sweep", "stop"} <= kinds
    assert "pivot_gated" in kinds
    ok, detail = first.ledger.verify()
    assert ok, detail
    _assert_decision_invariant(first)
