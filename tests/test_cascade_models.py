"""Tests for the Phase 17 (P17.2) additive cascade models (design section 14).

Everything here is pure model validation: no Docker, no network.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from aletheia.core.models import (
    ClusterDecision,
    EntityType,
    Hypothesis,
    HypothesisAssessment,
    HypothesisVerdict,
    IdentityTier,
    PivotCandidate,
    Provenance,
    RelationshipType,
    Seed,
    SeedType,
    SourceGrade,
)


def test_identity_tier_members_are_the_four_review_outcomes():
    assert {tier.value for tier in IdentityTier} == {"confirmed", "probable", "possible", "excluded"}


def test_new_relationship_types_exist_additively():
    assert RelationshipType.SAME_AS_CONFIRMED.value == "same_as_confirmed"
    assert RelationshipType.SAME_AS_EXCLUDED.value == "same_as_excluded"
    assert RelationshipType.PIVOTED_FROM.value == "pivoted_from"
    assert RelationshipType.SAME_AS_CANDIDATE.value == "same_as_candidate"


def test_provenance_cascade_defaults_keep_single_pass_meaning():
    provenance = Provenance(tool="sherlock", confidence=0.8, adapter_version="0.16.2")
    assert provenance.seed_index is None
    assert provenance.parent_finding_id is None
    assert provenance.cascade_depth == 0
    assert provenance.pivot_reason is None


def test_provenance_cascade_fields_round_trip():
    parent = uuid4()
    provenance = Provenance(
        tool="cascade",
        confidence=0.9,
        adapter_version="0.1",
        seed_index=2,
        cascade_depth=3,
        pivot_reason="profile link pivot",
        parent_finding_id=parent,
    )
    dumped = provenance.model_dump(mode="json")
    assert dumped["cascade_depth"] == 3
    assert dumped["pivot_reason"] == "profile link pivot"
    assert dumped["parent_finding_id"] == str(parent)
    assert Provenance.model_validate(dumped).parent_finding_id == parent


def test_provenance_rejects_negative_cascade_depth():
    with pytest.raises(ValueError):
        Provenance(tool="cascade", confidence=0.5, adapter_version="0.1", cascade_depth=-1)


def test_source_grade_admiralty_validation():
    grade = SourceGrade.unrated()
    assert grade.label == "F6"
    assert SourceGrade(reliability="a", credibility=1).label == "A1"
    with pytest.raises(ValueError):
        SourceGrade(reliability="Z", credibility=1)
    with pytest.raises(ValueError):
        SourceGrade(reliability="A", credibility=0)
    with pytest.raises(ValueError):
        SourceGrade(reliability="A", credibility=7)


def test_hypothesis_assessment_and_cluster_decision_validate():
    assessment = HypothesisAssessment(
        hypothesis=Hypothesis.SUBJECT,
        verdict=HypothesisVerdict.CONSISTENT,
        evidence=["claim:1"],
        rationale="rare handle plus shared phone",
    )
    decision = ClusterDecision(
        entity_ids=[uuid4(), uuid4()],
        tier=IdentityTier.CONFIRMED,
        accepted=True,
        score=7.5,
        assessments=[assessment],
    )
    assert decision.accepted is True
    assert decision.calibrated_probability is None
    assert decision.assessments[0].hypothesis is Hypothesis.SUBJECT
    with pytest.raises(ValueError):
        ClusterDecision(entity_ids=[uuid4()])
    with pytest.raises(ValueError):
        ClusterDecision(entity_ids=[uuid4(), uuid4()], calibrated_probability=2.0)


def test_pivot_candidate_carries_its_gate():
    pivot = PivotCandidate(
        claim_entity_type=EntityType.URL,
        claim_value="https://github.com/alice",
        seed=Seed(type=SeedType.URL, value="https://github.com/alice"),
        gate=IdentityTier.PROBABLE,
        reason="profile link",
    )
    assert pivot.seed.type is SeedType.URL
    assert pivot.gate is IdentityTier.PROBABLE
    assert pivot.parent_finding_id is None
    with pytest.raises(ValueError):
        PivotCandidate(
            claim_entity_type=EntityType.URL,
            claim_value="x",
            seed=Seed(type=SeedType.URL, value="https://example.test/x"),
        )
