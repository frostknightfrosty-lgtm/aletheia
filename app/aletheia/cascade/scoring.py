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
- Explicitly low-grade sources (Admiralty E/F labels on evidence items) get
  the same sentence-faithful cap, checked after the review-gate cap; the
  F6-unrated default is never attached, so ungraded sources are not capped
  merely for being ungraded (section 17, resolution item 7).
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
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone, tzinfo
from enum import StrEnum

from aletheia.core.calibration import Calibrator
from aletheia.core.models import IdentityTier

__all__ = [
    "DEFAULT_LIKELIHOOD_RATIOS",
    "LOW_GRADE_RELIABILITIES",
    "TEMPORAL_CONFIDENCE_BOOST",
    "TEMPORAL_MIN_SAMPLES",
    "TEMPORAL_OVERLAP_THRESHOLD",
    "EvidenceClass",
    "EvidenceItem",
    "ScoreResult",
    "TemporalCadence",
    "TierResult",
    "active_hour_histogram",
    "active_hour_overlap",
    "active_hours",
    "activity_histogram",
    "apply_temporal_boost",
    "boost_temporal_confidence",
    "compare_active_hours",
    "compare_activity_histograms",
    "extract_active_hours",
    "temporal_cadence_overlap",
    "temporal_cadence_similarity",
    "temporal_confidence_boost",
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

# Public-activity cadence (Phase 18.1). The comparison is deliberately a
# reviewable constant rather than a fitted model: three independent public
# timestamps per side is the minimum evidence that an hour histogram describes
# a habit, and a 70% histogram intersection is the v1 "significant" boundary.
TEMPORAL_CONFIDENCE_BOOST = 0.15
TEMPORAL_OVERLAP_THRESHOLD = 0.70
TEMPORAL_MIN_SAMPLES = 3

# Admiralty reliabilities that count as low-grade for the tier-gate cap
# (design section 6.3: "low-grade sources alone can never clear a tier gate").
LOW_GRADE_RELIABILITIES = frozenset({"E", "F"})

_GRADE_LABEL_RE = re.compile(r"[A-F][1-6]")


@dataclass(frozen=True)
class TemporalCadence:
    """The public-activity cadence comparison for one pair of profiles.

    ``left_hours``/``right_hours`` are the extracted UTC hours (0-23), and
    ``overlap`` is the histogram intersection of the two normalized 24-bin
    distributions. ``significant`` is true only when both sides have at least
    ``min_samples`` observations and ``overlap`` reaches the configured
    threshold, so a single shared timestamp can never manufacture a boost.
    """

    left_hours: tuple[int, ...]
    right_hours: tuple[int, ...]
    overlap: float
    significant: bool
    threshold: float

    @property
    def left_samples(self) -> int:
        return len(self.left_hours)

    @property
    def right_samples(self) -> int:
        return len(self.right_hours)

    @property
    def boost(self) -> float:
        return TEMPORAL_CONFIDENCE_BOOST if self.significant else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "left_hours": list(self.left_hours),
            "right_hours": list(self.right_hours),
            "left_samples": self.left_samples,
            "right_samples": self.right_samples,
            "overlap": self.overlap,
            "threshold": self.threshold,
            "significant": self.significant,
            "boost": self.boost,
        }


def _coerce_hour(value: int, tz: tzinfo) -> int:
    """Turn a numeric public timestamp into a UTC hour.

    Integers ``0..23`` are accepted directly as hours (handy for fixtures and
    for adapters that already bucket activity); larger values are treated as
    Unix timestamps. Out-of-range values raise ``ValueError``.
    """
    if 0 <= value <= 23:
        return int(value)
    try:
        stamp = datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"invalid activity timestamp: {value!r}") from exc
    return stamp.astimezone(tz).hour


def _coerce_timestamp(value: object, tz: tzinfo) -> int:
    """Extract the UTC hour from a datetime, ISO-8601 string, or Unix stamp."""
    if isinstance(value, datetime):
        stamp = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return stamp.astimezone(tz).hour
    if isinstance(value, bool):
        raise ValueError(f"invalid activity timestamp: {value!r}")
    if isinstance(value, (int, float)):
        return _coerce_hour(value, tz)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("empty activity timestamp")
        # A bare hour is useful in fixtures; an ISO date/time is the normal
        # adapter shape. Epoch numeric strings are accepted too.
        if text.isdigit() and len(text) <= 2:
            return _coerce_hour(int(text), tz)
        try:
            stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                return _coerce_hour(int(float(text)), tz)
            except ValueError as exc:
                raise ValueError(f"invalid activity timestamp: {value!r}") from exc
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(tz).hour
    raise ValueError(f"invalid activity timestamp: {value!r}")


def extract_active_hours(
    timestamps: Iterable[object],
    *,
    tz: tzinfo = timezone.utc,
) -> tuple[int, ...]:
    """Extract the public-activity hours (0-23) from timestamps.

    Invalid entries are skipped rather than guessed; callers that need to know
    how much public activity was usable can compare the returned tuple length
    with their input length. Naive datetimes are treated as UTC.
    """
    if isinstance(timestamps, (str, datetime, int, float)) and not isinstance(
        timestamps, bool
    ):
        timestamps = (timestamps,)
    hours: list[int] = []
    for value in timestamps:
        try:
            hours.append(_coerce_timestamp(value, tz))
        except ValueError:
            continue
    return tuple(hours)


def active_hours(timestamps: Iterable[object], *, tz: tzinfo = timezone.utc) -> tuple[int, ...]:
    """Alias for :func:`extract_active_hours` (public API readability)."""
    return extract_active_hours(timestamps, tz=tz)


def activity_histogram(
    timestamps: Iterable[object],
    *,
    tz: tzinfo = timezone.utc,
    normalize: bool = True,
) -> tuple[float, ...]:
    """A 24-bin activity histogram (normalized by default).

    The normalized form is a distribution over UTC hours, so profiles with
    different volumes of public activity are comparable. Set
    ``normalize=False`` for raw counts.
    """
    hours = extract_active_hours(timestamps, tz=tz)
    counts = [0] * 24
    for hour in hours:
        if 0 <= hour <= 23:
            counts[hour] += 1
    total = sum(counts)
    if not normalize:
        return tuple(float(count) for count in counts)
    if total == 0:
        return tuple(0.0 for _ in counts)
    return tuple(count / total for count in counts)


def active_hour_histogram(
    timestamps: Iterable[object],
    *,
    tz: tzinfo = timezone.utc,
    normalize: bool = True,
) -> tuple[float, ...]:
    """Alias for :func:`activity_histogram`."""
    return activity_histogram(timestamps, tz=tz, normalize=normalize)


def _histogram_intersection(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return min(1.0, sum(min(a, b) for a, b in zip(left, right)))


def compare_activity_histograms(
    left: Iterable[object],
    right: Iterable[object],
    *,
    threshold: float = TEMPORAL_OVERLAP_THRESHOLD,
    min_samples: int = TEMPORAL_MIN_SAMPLES,
    tz: tzinfo = timezone.utc,
) -> TemporalCadence:
    """Compare two public-activity histories by active-hour overlap.

    ``overlap`` is the histogram intersection of the two normalized 24-bin
    distributions. The comparison is significant only when both sides provide
    at least ``min_samples`` usable timestamps and ``overlap >= threshold``.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be in [0, 1]")
    if min_samples < 1:
        raise ValueError("min_samples must be >= 1")
    left_hours = extract_active_hours(left, tz=tz)
    right_hours = extract_active_hours(right, tz=tz)
    left_hist = activity_histogram(left_hours)
    right_hist = activity_histogram(right_hours)
    overlap = round(_histogram_intersection(left_hist, right_hist), 6)
    significant = (
        len(left_hours) >= min_samples
        and len(right_hours) >= min_samples
        and overlap >= threshold
    )
    return TemporalCadence(
        left_hours=left_hours,
        right_hours=right_hours,
        overlap=overlap,
        significant=significant,
        threshold=threshold,
    )


def temporal_cadence_overlap(
    left: Iterable[object],
    right: Iterable[object],
    *,
    threshold: float = TEMPORAL_OVERLAP_THRESHOLD,
    min_samples: int = TEMPORAL_MIN_SAMPLES,
    tz: tzinfo = timezone.utc,
) -> TemporalCadence:
    """Alias for :func:`compare_activity_histograms`."""
    return compare_activity_histograms(
        left, right, threshold=threshold, min_samples=min_samples, tz=tz
    )


def compare_active_hours(
    left: Iterable[object],
    right: Iterable[object],
    *,
    threshold: float = TEMPORAL_OVERLAP_THRESHOLD,
    min_samples: int = TEMPORAL_MIN_SAMPLES,
    tz: tzinfo = timezone.utc,
) -> TemporalCadence:
    """Alias for :func:`compare_activity_histograms`."""
    return compare_activity_histograms(
        left, right, threshold=threshold, min_samples=min_samples, tz=tz
    )


def active_hour_overlap(
    left: Iterable[object],
    right: Iterable[object],
    *,
    tz: tzinfo = timezone.utc,
) -> float:
    """Alias for :func:`temporal_cadence_similarity`."""
    return temporal_cadence_similarity(left, right, tz=tz)


def temporal_cadence_similarity(
    left: Iterable[object],
    right: Iterable[object],
    *,
    tz: tzinfo = timezone.utc,
) -> float:
    """The active-hour histogram intersection in [0, 1]."""
    return compare_activity_histograms(left, right, tz=tz).overlap


def temporal_confidence_boost(
    left: Iterable[object],
    right: Iterable[object],
    *,
    threshold: float = TEMPORAL_OVERLAP_THRESHOLD,
    min_samples: int = TEMPORAL_MIN_SAMPLES,
    tz: tzinfo = timezone.utc,
) -> float:
    """Return ``+0.15`` for a significant overlap, otherwise ``0.0``."""
    cadence = compare_activity_histograms(
        left, right, threshold=threshold, min_samples=min_samples, tz=tz
    )
    return TEMPORAL_CONFIDENCE_BOOST if cadence.significant else 0.0


def boost_temporal_confidence(
    left: Iterable[object],
    right: Iterable[object],
    *,
    threshold: float = TEMPORAL_OVERLAP_THRESHOLD,
    min_samples: int = TEMPORAL_MIN_SAMPLES,
    tz: tzinfo = timezone.utc,
) -> float:
    """Alias for :func:`temporal_confidence_boost` (returns 0.0 or +0.15)."""
    return temporal_confidence_boost(
        left, right, threshold=threshold, min_samples=min_samples, tz=tz
    )


def apply_temporal_boost(
    score: float,
    left: Iterable[object],
    right: Iterable[object],
    *,
    threshold: float = TEMPORAL_OVERLAP_THRESHOLD,
    min_samples: int = TEMPORAL_MIN_SAMPLES,
    boost: float = TEMPORAL_CONFIDENCE_BOOST,
    cap: float = 1.0,
    tz: tzinfo = timezone.utc,
) -> tuple[float, TemporalCadence]:
    """Add the documented cadence boost to a fuzzy-match confidence.

    The boost is applied only when the comparison is significant. Returned
    scores are rounded to six decimals and capped at ``cap`` (1.0 by default).
    """
    cadence = compare_activity_histograms(
        left, right, threshold=threshold, min_samples=min_samples, tz=tz
    )
    if not cadence.significant:
        return round(float(score), 6), cadence
    return min(float(cap), round(float(score) + float(boost), 6)), cadence


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence for a same-identity hypothesis.

    ``source_grade_label`` is the Admiralty label (e.g. ``"B2"``) of the
    producing source *when a producer actually graded it*. It is deliberately
    ``None`` for ungraded sources: the F6-unrated default means "not yet
    graded", not "judged unreliable" (``docs/PIVOT_CASCADE.md`` section 17,
    resolution item 7), so the low-grade cap only ever fires on explicit
    E/F labels.
    """

    evidence_class: EvidenceClass
    reason: str
    origin: str
    similarity: float | None = None
    weight: float = 1.0
    review_gated: bool = False
    source_grade_label: str | None = None

    def __post_init__(self) -> None:
        if not self.origin:
            raise ValueError("evidence origin must be non-empty (it keys independence)")
        if not 0.0 < self.weight <= 1.0:
            raise ValueError("evidence weight must be in (0, 1]")
        if self.source_grade_label is not None and not _GRADE_LABEL_RE.fullmatch(
            self.source_grade_label
        ):
            raise ValueError("source_grade_label must look like an Admiralty label (A1..F6)")

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
    """The tier a member set reaches, with both gate caps made explicit."""

    tier: IdentityTier | None
    capped_by_review_gate: bool
    capped_by_low_grade: bool = False
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
    capped_by_low_grade: bool
    calibrated: bool
    probability: float | None
    tier_notes: tuple[str, ...] = field(default=())


def _independent_counts(items: Iterable[EvidenceItem]) -> dict[EvidenceClass, int]:
    """Per-class count of distinct origins (an origin never counts twice)."""
    seen: dict[EvidenceClass, set[str]] = {}
    for item in items:
        seen.setdefault(item.evidence_class, set()).add(item.origin)
    return {evidence_class: len(origins) for evidence_class, origins in seen.items()}


def _is_low_grade(item: EvidenceItem) -> bool:
    """True only when a producer explicitly graded the source E or F.

    The F6-unrated default is never attached to evidence items
    (``docs/PIVOT_CASCADE.md`` section 17, resolution item 7): "not yet
    graded" is not the same statement as "judged unreliable".
    """
    label = item.source_grade_label
    return label is not None and label[0] in LOW_GRADE_RELIABILITIES


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
    """The tier the evidence reaches, capped when only exempt classes clear it.

    Two axis-specific caps apply, each sentence-faithful to section 6.3: the
    tier must be justified by evidence with review-gated items set aside, and
    by evidence with explicitly low-grade (E/F) items set aside; the reported
    tier is the weaker of the two per-axis tiers, and each flag records
    whether its axis was binding. Vetoes are checked per axis the same way
    (an exclusion survives an axis only when the remaining items still veto).
    """
    materialized = tuple(items)
    tier_full = _tier_from_counts(_independent_counts(materialized))
    if tier_full is None:
        return TierResult(tier=None, capped_by_review_gate=False, capped_by_low_grade=False)
    tier_no_gated = _tier_from_counts(
        _independent_counts(item for item in materialized if not item.review_gated)
    )
    tier_no_low = _tier_from_counts(
        _independent_counts(item for item in materialized if not _is_low_grade(item))
    )
    capped_by_review_gate = tier_no_gated is not tier_full
    capped_by_low_grade = tier_no_low is not tier_full
    notes: list[str] = []
    if capped_by_review_gate:
        notes.append("review-gated evidence cannot clear a tier gate alone")
    if capped_by_low_grade:
        notes.append("low-grade sources alone cannot clear a tier gate")
    if tier_full is IdentityTier.EXCLUDED:
        gated_stands = tier_no_gated is IdentityTier.EXCLUDED
        low_stands = tier_no_low is IdentityTier.EXCLUDED
        if gated_stands and low_stands:
            tier: IdentityTier | None = IdentityTier.EXCLUDED
        elif gated_stands:
            tier = tier_no_low
        elif low_stands:
            tier = tier_no_gated
        else:
            tier = _weaker_tier(tier_no_gated, tier_no_low)
    else:
        tier = _weaker_tier(tier_no_gated, tier_no_low)
    return TierResult(
        tier=tier,
        capped_by_review_gate=capped_by_review_gate,
        capped_by_low_grade=capped_by_low_grade,
        notes=tuple(notes),
    )


_TIER_ORDER: dict[IdentityTier | None, int] = {
    None: 0,
    IdentityTier.POSSIBLE: 1,
    IdentityTier.PROBABLE: 2,
    IdentityTier.CONFIRMED: 3,
}


def _weaker_tier(left: IdentityTier | None, right: IdentityTier | None) -> IdentityTier | None:
    """The lower of two tiers by ordinal (never called with EXCLUDED)."""
    return left if _TIER_ORDER[left] <= _TIER_ORDER[right] else right


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
        capped_by_low_grade=tier_result.capped_by_low_grade,
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
