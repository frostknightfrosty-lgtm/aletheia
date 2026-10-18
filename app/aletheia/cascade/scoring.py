"""Likelihood-ratio scoring, tiers, and the calibration hook (Phase 17, P17.4).

Design of record: ``docs/PIVOT_CASCADE.md`` sections 6.2 and 6.3.

- Each evidence item carries a class (HARD / STRONG / MEDIUM / WEAK / VETO)
  and the score is the sum of per-class log-likelihood ratios
  (Fellegi-Sunter form). The v1 ratio table below is a *reviewable constant
  table*, not a fitted model — calibration lands when labels exist.
- Review-gated evidence (section 10.1 expansions: face search, endpoint
  existence, exposure signals) corroborates but can never clear a tier gate
  alone. Tiers are computed twice — with and without gated items — and a tier
  that only the gated subset reaches is reported as capped at the open tier.
- Tiers follow section 6.3's counts: **confirmed** (>= 1 HARD, or >= 2
  independent STRONG), **probable** (1 STRONG + >= 1 MEDIUM, or >= 3
  independent MEDIUM), **possible** (anything above WEAK), **excluded** (any
  veto). "Independent" = distinct evidence origins; origins are built from
  the producing adapter and claim, so two echoes of the same observation
  never count twice. This reading is provisional v1 and documented as such.
- VETO items are never summed; they exclude directly. The falsification pass
  that produces surviving vetoes is P17.5; this module just honours them.
- The calibration hook reuses :class:`aletheia.core.calibration.Calibrator`:
  a probability is reported only when the calibrator was actually fitted;
  otherwise ``calibrated`` stays ``False`` and ``probability`` is ``None``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from aletheia.core.calibration import Calibrator
from aletheia.core.models import IdentityTier

__all__ = [
    "DEFAULT_LIKELIHOOD_RATIOS",
    "EvidenceClass",
    "EvidenceItem",
    "ScoreResult",
    "TierResult",
    "score_evidence",
    "tier_for",
]


class EvidenceClass(StrEnum):
    """Evidence strength classes (design section 6.2)."""

    HARD = "hard"
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    VETO = "veto"


# Provisional v1 likelihood ratios (reviewable constants, not fitted values).
# VETO has no ratio: vetoes exclude directly and are never summed.
DEFAULT_LIKELIHOOD_RATIOS: dict[EvidenceClass, float] = {
    EvidenceClass.HARD: 50.0,
    EvidenceClass.STRONG: 10.0,
    EvidenceClass.MEDIUM: 3.0,
    EvidenceClass.WEAK: 1.5,
    EvidenceClass.VETO: 1.0,
}


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence for a same-identity hypothesis."""

    evidence_class: EvidenceClass
    reason: str
    origin: str
    similarity: float | None = None
    weight: float = 1.0
    review_gated: bool = False

    def __post_init__(self) -> None:
        if not self.origin:
            raise ValueError("evidence origin must be non-empty (it keys independence)")
        if not 0.0 < self.weight <= 1.0:
            raise ValueError("evidence weight must be in (0, 1]")

    def log_lr(self, table: Mapping[EvidenceClass, float] | None = None) -> float:
        """This item's log-likelihood-ratio contribution (vetoes excluded)."""
        if self.evidence_class is EvidenceClass.VETO:
            raise ValueError("vetoes are not summed; read ScoreResult.excluded")
        ratios = DEFAULT_LIKELIHOOD_RATIOS if table is None else table
        ratio = ratios[self.evidence_class]
        if ratio <= 0.0:
            raise ValueError(f"non-positive likelihood ratio for {self.evidence_class}")
        return math.log(ratio) * self.weight


@dataclass(frozen=True)
class TierResult:
    """The tier a member set reaches, with the review-gate cap made explicit."""

    tier: IdentityTier | None
    capped_by_review_gate: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoreResult:
    """The scored outcome for one candidate pair or cluster member."""

    log_lr_total: float
    counts: Mapping[EvidenceClass, int]
    open_counts: Mapping[EvidenceClass, int]
    vetoes: tuple[str, ...]
    excluded: bool
    tier: IdentityTier | None
    capped_by_review_gate: bool
    calibrated: bool
    probability: float | None
    tier_notes: tuple[str, ...] = field(default=())


def _independent_counts(items: Iterable[EvidenceItem]) -> dict[EvidenceClass, int]:
    """Per-class count of distinct origins (an origin never counts twice)."""
    seen: dict[EvidenceClass, set[str]] = {}
    for item in items:
        seen.setdefault(item.evidence_class, set()).add(item.origin)
    return {evidence_class: len(origins) for evidence_class, origins in seen.items()}


def _tier_from_counts(counts: Mapping[EvidenceClass, int]) -> IdentityTier | None:
    hard = counts.get(EvidenceClass.HARD, 0)
    strong = counts.get(EvidenceClass.STRONG, 0)
    medium = counts.get(EvidenceClass.MEDIUM, 0)
    if counts.get(EvidenceClass.VETO, 0) > 0:
        return IdentityTier.EXCLUDED
    if hard >= 1 or strong >= 2:
        return IdentityTier.CONFIRMED
    if (strong >= 1 and medium >= 1) or medium >= 3:
        return IdentityTier.PROBABLE
    if hard or strong or medium:
        return IdentityTier.POSSIBLE
    return None  # weak-only evidence does not reach a tier


def tier_for(items: Iterable[EvidenceItem]) -> TierResult:
    """The tier the evidence reaches, capped when only gated items clear it."""
    materialized = tuple(items)
    tier_all = _tier_from_counts(_independent_counts(materialized))
    tier_open = _tier_from_counts(
        _independent_counts(item for item in materialized if not item.review_gated)
    )
    if tier_all is tier_open:
        return TierResult(tier=tier_all, capped_by_review_gate=False)
    if tier_all is None:
        return TierResult(tier=None, capped_by_review_gate=False)
    return TierResult(
        tier=tier_open,
        capped_by_review_gate=True,
        notes=("review-gated evidence cannot clear a tier gate alone",),
    )


def score_evidence(
    items: Iterable[EvidenceItem],
    *,
    table: Mapping[EvidenceClass, float] | None = None,
    calibrator: Calibrator | None = None,
    prior_log_odds: float = 0.0,
) -> ScoreResult:
    """Score a set of evidence items into a :class:`ScoreResult`.

    ``prior_log_odds`` comes from :mod:`aletheia.cascade.priors`; the total
    (prior + evidence log-LRs) is what the calibrator would map to a
    probability, and only a fitted calibrator produces one.
    """
    materialized = tuple(items)
    total = float(prior_log_odds)
    vetoes: list[str] = []
    for item in materialized:
        if item.evidence_class is EvidenceClass.VETO:
            vetoes.append(item.reason)
            continue
        total += item.log_lr(table)
    tier_result = tier_for(materialized)
    probability: float | None = None
    calibrated = False
    if calibrator is not None and calibrator.trained:
        probability = float(calibrator.predict(total))
        calibrated = True
    return ScoreResult(
        log_lr_total=total,
        counts=_raw_counts(materialized),
        open_counts=_raw_counts(item for item in materialized if not item.review_gated),
        vetoes=tuple(vetoes),
        excluded=bool(vetoes),
        tier=tier_result.tier,
        capped_by_review_gate=tier_result.capped_by_review_gate,
        calibrated=calibrated,
        probability=probability,
        tier_notes=tier_result.notes,
    )


def _raw_counts(items: Iterable[EvidenceItem]) -> dict[EvidenceClass, int]:
    """Per-class item counts (every item; transparency counters, not tier logic)."""
    counts: dict[EvidenceClass, int] = {}
    for item in items:
        counts[item.evidence_class] = counts.get(item.evidence_class, 0) + 1
    return counts
