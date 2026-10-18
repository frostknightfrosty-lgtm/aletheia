"""Analysis of Competing Hypotheses (Phase 17, P17.5).

Design of record: ``docs/PIVOT_CASCADE.md`` section 6.3 — each hit is scored
against ``H_subject`` (belongs to the investigation subject), ``H_other``
(different person), and ``H_shared`` (shared/sockpuppet account); a merge
requires ``H_subject`` to survive with a margin over the best alternative,
and the report shows the surviving hypothesis and what would falsify it.

Contribution table (provisional v1 constants, reviewable):

| Evidence | H_subject | H_other | H_shared |
| --- | --- | --- | --- |
| HARD | +3.0 | -3.0 | +1.5 |
| STRONG | +2.0 | -2.0 | +1.0 |
| MEDIUM | +1.0 | -0.5 | +0.5 |
| WEAK | +0.5 | 0.0 | 0.0 |
| VETO | -3.0 | +3.0 | +1.5 |

Reading of the table: same-person evidence supports ``H_subject`` fully and
disconfirms ``H_other``; it supports ``H_shared`` at half weight (a shared
account shows the subject's signals, but not every signal need come from the
subject); conflicts support ``H_other`` fully and ``H_shared`` at half
weight (an isolated conflict is better explained by "different person" than
by "shared account"; sharing gains support only alongside same-person
evidence).

``surviving`` is the leading hypothesis only when it leads the runner-up by
at least ``margin``; ties resolve conservatively against ``H_subject`` and
an underdetermined outcome returns ``None``. Merges additionally require the
tier gate (``scoring.tier_for``) — this module only answers the ACH
question, and callers combine both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from aletheia.cascade.scoring import EvidenceClass, EvidenceItem
from aletheia.core.models import Hypothesis, HypothesisAssessment, HypothesisVerdict

__all__ = ["DEFAULT_MARGIN", "AchOutcome", "assess_hypotheses"]

DEFAULT_MARGIN = 1.0

_SUBJECT_WEIGHTS: dict[EvidenceClass, float] = {
    EvidenceClass.HARD: 3.0,
    EvidenceClass.STRONG: 2.0,
    EvidenceClass.MEDIUM: 1.0,
    EvidenceClass.WEAK: 0.5,
    EvidenceClass.VETO: -3.0,
}
_OTHER_WEIGHTS: dict[EvidenceClass, float] = {
    EvidenceClass.HARD: -3.0,
    EvidenceClass.STRONG: -2.0,
    EvidenceClass.MEDIUM: -0.5,
    EvidenceClass.WEAK: 0.0,
    EvidenceClass.VETO: 3.0,
}
_SHARED_WEIGHTS: dict[EvidenceClass, float] = {
    EvidenceClass.HARD: 1.5,
    EvidenceClass.STRONG: 1.0,
    EvidenceClass.MEDIUM: 0.5,
    EvidenceClass.WEAK: 0.0,
    EvidenceClass.VETO: 1.5,
}

# Conservative resolution order: on exact ties the alternative explanations
# are ranked first, so a tie can never favour a merge.
_TIE_ORDER = (Hypothesis.OTHER, Hypothesis.SHARED, Hypothesis.SUBJECT)

_FALSIFIERS: dict[Hypothesis, str] = {
    Hypothesis.SUBJECT: (
        "a conflicting rare identifier, demographic, or era contradiction "
        "between the accounts (VETO-class evidence)"
    ),
    Hypothesis.OTHER: (
        "a shared rare identifier (identical email or phone) or two "
        "independent STRONG signals"
    ),
    Hypothesis.SHARED: (
        "mutually exclusive self-declarations by two different persons "
        "(conflicting demographics, exclusive commitments)"
    ),
}


@dataclass(frozen=True)
class AchOutcome:
    """The scored hypothesis set with the margin decision made explicit."""

    surviving: Hypothesis | None
    scores: Mapping[Hypothesis, float]
    margin_required: float
    assessments: tuple[HypothesisAssessment, ...]
    falsifier: str | None
    rationale: str


def _assessment(
    hypothesis: Hypothesis,
    weights: Mapping[EvidenceClass, float],
    evidence: Sequence[EvidenceItem],
) -> tuple[HypothesisAssessment, float]:
    consistent = 0.0
    inconsistent = 0.0
    lines: list[str] = []
    for item in evidence:
        contribution = weights[item.evidence_class] * item.weight
        if contribution > 0.0:
            consistent += contribution
            lines.append(f"consistent: {item.reason} ({item.evidence_class.value})")
        elif contribution < 0.0:
            inconsistent += -contribution
            lines.append(f"inconsistent: {item.reason} ({item.evidence_class.value})")
    if consistent > inconsistent:
        verdict = HypothesisVerdict.CONSISTENT
    elif inconsistent > consistent:
        verdict = HypothesisVerdict.INCONSISTENT
    else:
        verdict = HypothesisVerdict.NEUTRAL
    rationale = f"weighted support {consistent:.2f} vs contradiction {inconsistent:.2f}"
    return (
        HypothesisAssessment(
            hypothesis=hypothesis,
            verdict=verdict,
            evidence=lines,
            rationale=rationale,
        ),
        consistent - inconsistent,
    )


def assess_hypotheses(
    evidence: Sequence[EvidenceItem],
    *,
    margin: float = DEFAULT_MARGIN,
) -> AchOutcome:
    """Score the three hypotheses and decide whether one leads by the margin."""
    if margin < 0.0:
        raise ValueError("margin must be >= 0")
    materialized = tuple(evidence)
    scores: dict[Hypothesis, float] = {}
    assessments: list[HypothesisAssessment] = []
    for hypothesis, weights in (
        (Hypothesis.SUBJECT, _SUBJECT_WEIGHTS),
        (Hypothesis.OTHER, _OTHER_WEIGHTS),
        (Hypothesis.SHARED, _SHARED_WEIGHTS),
    ):
        assessment, net = _assessment(hypothesis, weights, materialized)
        assessments.append(assessment)
        scores[hypothesis] = net
    ranked = sorted(scores, key=lambda hypothesis: (-scores[hypothesis], _TIE_ORDER.index(hypothesis)))
    winner, runner_up = ranked[0], ranked[1]
    lead = scores[winner] - scores[runner_up]
    if lead >= margin:
        falsifier = _FALSIFIERS[winner]
        rationale = (
            f"{winner.value} leads {runner_up.value} by {lead:.2f} "
            f"(margin {margin:.2f}); falsifier: {falsifier}"
        )
    else:
        falsifier = None
        rationale = (
            f"underdetermined: {winner.value} leads {runner_up.value} by "
            f"{lead:.2f}, below the {margin:.2f} margin"
        )
    return AchOutcome(
        surviving=winner if lead >= margin else None,
        scores=scores,
        margin_required=margin,
        assessments=tuple(assessments),
        falsifier=falsifier,
        rationale=rationale,
    )
