"""Tests for likelihood-ratio scoring, tiers, priors, and the calibration hook (P17.4)."""

from __future__ import annotations

import math

import pytest

from aletheia.cascade.priors import (
    candidate_prior,
    handle_entropy_bits,
    handle_prior_log_odds,
    name_prior_log_odds,
    shannon_bits,
)
from aletheia.cascade.scoring import (
    DEFAULT_LIKELIHOOD_RATIOS,
    EvidenceClass,
    EvidenceItem,
    score_evidence,
    tier_for,
)
from aletheia.core.calibration import Calibrator
from aletheia.core.models import IdentityTier


def _item(evidence_class: EvidenceClass, origin: str = "adapter|seed=0|email", **kwargs):
    kwargs.setdefault("reason", "test evidence")
    return EvidenceItem(evidence_class=evidence_class, origin=origin, **kwargs)


def test_evidence_item_validation():
    with pytest.raises(ValueError):
        _item(EvidenceClass.HARD, origin="")
    with pytest.raises(ValueError):
        _item(EvidenceClass.HARD, weight=0.0)
    with pytest.raises(ValueError):
        _item(EvidenceClass.HARD, weight=1.5)


def test_evidence_log_lr_uses_table_and_weight():
    heavy = _item(EvidenceClass.STRONG)
    half = _item(EvidenceClass.STRONG, weight=0.5)
    assert heavy.log_lr() == pytest.approx(math.log(10.0))
    assert half.log_lr() == pytest.approx(0.5 * math.log(10.0))
    assert heavy.log_lr() == pytest.approx(heavy.log_lr(DEFAULT_LIKELIHOOD_RATIOS))


def test_veto_log_lr_raises_and_default_table_is_ordered():
    with pytest.raises(ValueError):
        _item(EvidenceClass.VETO).log_lr()
    ratios = DEFAULT_LIKELIHOOD_RATIOS
    assert (
        ratios[EvidenceClass.HARD]
        > ratios[EvidenceClass.STRONG]
        > ratios[EvidenceClass.MEDIUM]
        > ratios[EvidenceClass.WEAK]
        >= 1.0
    )


def test_score_evidence_sums_prior_and_evidence():
    items = [
        _item(EvidenceClass.STRONG, origin="a|seed=0|email"),
        _item(EvidenceClass.MEDIUM, origin="b|seed=1|name", weight=0.5),
    ]
    result = score_evidence(items, prior_log_odds=1.0)
    assert result.log_lr_total == pytest.approx(1.0 + math.log(10.0) + 0.5 * math.log(3.0))
    assert result.excluded is False
    assert result.vetoes == ()
    assert result.counts[EvidenceClass.STRONG] == 1
    assert result.calibrated is False
    assert result.probability is None


def test_score_evidence_vetoes_exclude_without_summing():
    items = [
        _item(EvidenceClass.STRONG, origin="a|seed=0|email"),
        _item(EvidenceClass.VETO, origin="b|seed=1|name", reason="conflicting names"),
    ]
    result = score_evidence(items)
    assert result.excluded is True
    assert result.vetoes == ("conflicting names",)
    assert result.log_lr_total == pytest.approx(math.log(10.0))
    assert result.tier is IdentityTier.EXCLUDED
    assert result.capped_by_review_gate is False


def test_tier_confirmed_by_single_hard():
    result = tier_for([_item(EvidenceClass.HARD)])
    assert result.tier is IdentityTier.CONFIRMED
    assert result.capped_by_review_gate is False


def test_tier_independent_strong_requires_two_origins():
    one_origin = [
        _item(EvidenceClass.STRONG, origin="same|claim"),
        _item(EvidenceClass.STRONG, origin="same|claim"),
    ]
    assert tier_for(one_origin).tier is IdentityTier.POSSIBLE
    two_origins = [
        _item(EvidenceClass.STRONG, origin="a|seed=0|email"),
        _item(EvidenceClass.STRONG, origin="b|seed=1|username"),
    ]
    assert tier_for(two_origins).tier is IdentityTier.CONFIRMED


def test_tier_probable_paths():
    strong_plus_medium = [
        _item(EvidenceClass.STRONG, origin="a|seed=0|email"),
        _item(EvidenceClass.MEDIUM, origin="b|seed=1|name"),
    ]
    assert tier_for(strong_plus_medium).tier is IdentityTier.PROBABLE
    three_medium = [
        _item(EvidenceClass.MEDIUM, origin=f"adapter{i}|seed={i}|name") for i in range(3)
    ]
    assert tier_for(three_medium).tier is IdentityTier.PROBABLE
    two_medium = [
        _item(EvidenceClass.MEDIUM, origin=f"adapter{i}|seed={i}|name") for i in range(2)
    ]
    assert tier_for(two_medium).tier is IdentityTier.POSSIBLE


def test_tier_possible_and_none():
    assert tier_for([_item(EvidenceClass.WEAK)]).tier is None
    assert tier_for([]).tier is None
    assert tier_for([_item(EvidenceClass.MEDIUM)]).tier is IdentityTier.POSSIBLE


def test_review_gated_cannot_clear_gate_alone():
    mixed = [
        _item(EvidenceClass.STRONG, origin="a|seed=0|email"),
        _item(EvidenceClass.STRONG, origin="b|seed=1|face", review_gated=True),
    ]
    result = tier_for(mixed)
    assert result.tier is IdentityTier.POSSIBLE
    assert result.capped_by_review_gate is True
    assert any("review-gated" in note for note in result.notes)
    open_only = [
        _item(EvidenceClass.STRONG, origin="a|seed=0|email"),
        _item(EvidenceClass.STRONG, origin="b|seed=1|username"),
    ]
    assert tier_for(open_only).tier is IdentityTier.CONFIRMED
    assert tier_for(open_only).capped_by_review_gate is False
    gated_only = [_item(EvidenceClass.HARD, origin="x|seed=0|face", review_gated=True)]
    gated_result = tier_for(gated_only)
    assert gated_result.tier is None
    assert gated_result.capped_by_review_gate is True


def test_review_gate_cap_reported_in_score():
    items = [
        _item(EvidenceClass.STRONG, origin="a|seed=0|email"),
        _item(EvidenceClass.STRONG, origin="b|seed=1|face", review_gated=True),
    ]
    result = score_evidence(items)
    assert result.capped_by_review_gate is True
    assert result.tier is IdentityTier.POSSIBLE
    assert result.open_counts[EvidenceClass.STRONG] == 1
    assert result.counts[EvidenceClass.STRONG] == 2


def test_calibrator_untrained_reports_no_probability():
    calibrator = Calibrator()
    assert calibrator.trained is False
    result = score_evidence([_item(EvidenceClass.HARD)], calibrator=calibrator)
    assert result.calibrated is False
    assert result.probability is None


def test_calibrator_trained_reports_bounded_monotone_probability():
    calibrator = Calibrator()
    calibrator.fit(
        [(-4.0, 0), (-3.0, 0), (-2.0, 0), (-1.0, 0), (1.0, 1), (2.0, 1), (3.0, 1), (4.0, 1)]
    )
    assert calibrator.trained is True
    strong = score_evidence([_item(EvidenceClass.HARD)], calibrator=calibrator)
    weak = score_evidence([_item(EvidenceClass.WEAK)], calibrator=calibrator)
    assert strong.calibrated is True
    assert strong.probability is not None and 0.0 <= strong.probability <= 1.0
    assert weak.probability is not None and 0.0 <= weak.probability <= 1.0
    assert strong.probability >= weak.probability


def test_handle_entropy_priors_are_monotone_and_signed():
    assert shannon_bits("") == 0.0
    assert shannon_bits("aaaa") == 0.0
    assert handle_entropy_bits("frost") < handle_entropy_bits("frost2233")
    low = handle_prior_log_odds("frost")
    high = handle_prior_log_odds("frost2233")
    assert low.log_odds < 0.0 < high.log_odds
    assert low.calibrated is False
    assert low.notes
    adjusted = handle_prior_log_odds("frost", platform_adjustment=1.5)
    assert adjusted.log_odds == pytest.approx(low.log_odds + 1.5)


def test_candidate_prior_combines_handle_name_and_platform_terms():
    result = candidate_prior(
        handles=("frost2233", "frost2233"),
        names=("Alice Smith",),
        rarity={"smith": 0.01},
        platform_adjustment=0.25,
    )
    expected = (
        handle_prior_log_odds("frost2233").log_odds
        + 0.25 * -math.log2(0.01)
        + 0.25
    )
    assert result.log_odds == pytest.approx(expected)
    assert result.calibrated is False
    assert any("uncalibrated" in note for note in result.notes)


def test_name_prior_missing_table_and_unknown_tokens():
    no_table = name_prior_log_odds("Alice Smith", rarity=None)
    assert no_table.log_odds == 0.0
    assert any("no name-rarity table" in note for note in no_table.notes)
    partial = name_prior_log_odds("Alice Smith", rarity={"smith": 0.02})
    assert partial.log_odds == pytest.approx(0.25 * -math.log2(0.02))
    assert any("alice" in note for note in partial.notes)
    unknown = name_prior_log_odds("Qwerty Zxcvb", rarity={"smith": 0.02})
    assert unknown.log_odds == 0.0


def test_low_grade_sources_cannot_clear_a_gate_alone():
    items = [
        _item(EvidenceClass.HARD, origin="a|seed=0|record", source_grade_label="E2"),
        _item(EvidenceClass.STRONG, origin="b|seed=1|email"),
    ]
    result = tier_for(items)
    assert result.tier is IdentityTier.POSSIBLE
    assert result.capped_by_low_grade is True
    assert any("low-grade" in note for note in result.notes)
    scored = score_evidence(items)
    assert scored.capped_by_low_grade is True
    assert scored.tier is IdentityTier.POSSIBLE


def test_clean_hard_confirms_alongside_a_low_grade_hard():
    items = [
        _item(EvidenceClass.HARD, origin="a|seed=0|record", source_grade_label="F6"),
        _item(EvidenceClass.HARD, origin="b|seed=1|email"),
    ]
    result = tier_for(items)
    assert result.tier is IdentityTier.CONFIRMED
    assert result.capped_by_low_grade is False


def test_ungraded_items_are_not_capped_for_being_ungraded():
    items = [
        _item(EvidenceClass.STRONG, origin="a|seed=0|email"),
        _item(EvidenceClass.STRONG, origin="b|seed=1|username"),
    ]
    result = tier_for(items)
    assert result.tier is IdentityTier.CONFIRMED
    assert result.capped_by_low_grade is False


def test_grade_label_must_look_like_an_admiralty_label():
    with pytest.raises(ValueError):
        _item(EvidenceClass.HARD, source_grade_label="Z9")
    with pytest.raises(ValueError):
        _item(EvidenceClass.HARD, source_grade_label="B")
