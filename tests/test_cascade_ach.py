"""Tests for the ACH hypothesis scoring (P17.5)."""

from __future__ import annotations

import pytest

from aletheia.cascade.ach import DEFAULT_MARGIN, assess_hypotheses
from aletheia.cascade.scoring import EvidenceClass, EvidenceItem
from aletheia.core.models import Hypothesis, HypothesisVerdict


def _item(evidence_class: EvidenceClass, origin: str, **kwargs):
    kwargs.setdefault("reason", "test evidence")
    return EvidenceItem(evidence_class=evidence_class, origin=origin, **kwargs)


def test_two_strong_survive_subject_with_margin():
    outcome = assess_hypotheses(
        [
            _item(EvidenceClass.STRONG, "a|seed=0|email"),
            _item(EvidenceClass.STRONG, "b|seed=1|username"),
        ]
    )
    assert outcome.surviving is Hypothesis.SUBJECT
    assert outcome.scores[Hypothesis.SUBJECT] == pytest.approx(4.0)
    assert outcome.scores[Hypothesis.SHARED] == pytest.approx(2.0)
    assert outcome.scores[Hypothesis.OTHER] == pytest.approx(-4.0)
    assert outcome.falsifier is not None
    assert "conflicting rare identifier" in outcome.falsifier
    assert outcome.margin_required == DEFAULT_MARGIN


def test_single_strong_survives_at_exact_margin():
    outcome = assess_hypotheses([_item(EvidenceClass.STRONG, "a|seed=0|email")])
    assert outcome.surviving is Hypothesis.SUBJECT
    assert outcome.scores[Hypothesis.SUBJECT] - outcome.scores[Hypothesis.SHARED] == pytest.approx(
        1.0
    )


def test_single_medium_and_empty_are_underdetermined():
    medium = assess_hypotheses([_item(EvidenceClass.MEDIUM, "a|seed=0|name")])
    assert medium.surviving is None
    assert medium.falsifier is None
    assert "underdetermined" in medium.rationale
    empty = assess_hypotheses([])
    assert empty.surviving is None


def test_veto_alone_resolves_to_other():
    outcome = assess_hypotheses([_item(EvidenceClass.VETO, "a|seed=0|name")])
    assert outcome.surviving is Hypothesis.OTHER
    assert outcome.falsifier is not None
    assert "shared rare identifier" in outcome.falsifier


def test_two_strong_plus_veto_prefers_shared_no_merge():
    outcome = assess_hypotheses(
        [
            _item(EvidenceClass.STRONG, "a|seed=0|email"),
            _item(EvidenceClass.STRONG, "b|seed=1|username"),
            _item(EvidenceClass.VETO, "c|seed=2|name"),
        ]
    )
    assert outcome.scores[Hypothesis.SHARED] == pytest.approx(3.5)
    assert outcome.surviving is Hypothesis.SHARED
    assert outcome.falsifier is not None
    assert "exclusive commitments" in outcome.falsifier


def test_margin_parameter_and_validation():
    strict = assess_hypotheses(
        [_item(EvidenceClass.STRONG, "a|seed=0|email")], margin=3.0
    )
    assert strict.surviving is None
    with pytest.raises(ValueError):
        assess_hypotheses([], margin=-0.1)


def test_assessments_record_verdicts_and_lines():
    outcome = assess_hypotheses(
        [
            _item(EvidenceClass.STRONG, "a|seed=0|email"),
            _item(EvidenceClass.VETO, "b|seed=1|name"),
        ]
    )
    by_hypothesis = {assessment.hypothesis: assessment for assessment in outcome.assessments}
    subject = by_hypothesis[Hypothesis.SUBJECT]
    assert subject.verdict is HypothesisVerdict.INCONSISTENT
    assert any(line.startswith("consistent:") for line in subject.evidence)
    assert any(line.startswith("inconsistent:") for line in subject.evidence)
    shared = by_hypothesis[Hypothesis.SHARED]
    assert shared.verdict is HypothesisVerdict.CONSISTENT
    other = by_hypothesis[Hypothesis.OTHER]
    assert other.verdict is HypothesisVerdict.CONSISTENT
