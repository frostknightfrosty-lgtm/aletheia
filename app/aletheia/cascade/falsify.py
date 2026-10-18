"""Falsification-first review pass (Phase 17, P17.5).

Design of record: ``docs/PIVOT_CASCADE.md`` section 6.3 — "before confirming,
a dedicated review pass runs disconfirming probes (rare-attribute conflicts,
era contradictions, name conflicts) and records the strongest disconfirming
evidence in the ledger."

The pass is pure and additive: it reads a pair of claim sets (plus optional
activity eras) and returns VETO-class evidence items for hard contradictions,
soft warnings for weaker disconfirming signals, and one ledger line naming
the strongest disconfirming evidence. Nothing is removed or rewritten; the
scoring module keeps vetoes out of the summed likelihood ratios.

v1 probe set (reviewable; extend as calibration data arrives):

- **cross-claim veto sweep** — the conflict rules of the evidence table
  (variant-inequivalent name conflicts with Jaro-Winkler < 0.5, conflicting
  VINs) run over the full left x right claim cross product; only VETO items
  are collected, deduplicated by (reason, origin).
- **attribute contradictions** — single-valued attributes that cannot differ
  between two records of one person: ``date_of_birth`` and ``national_id``
  (the documented v1 set). Different non-empty values veto.
- **era coherence** — when both sides expose an activity window and the
  windows do not overlap at all, a soft warning is recorded. Disjoint eras
  are deliberately *not* a veto: people leave platforms.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from aletheia.cascade.claims import Claim, pair_origin_key
from aletheia.cascade.evidence import compare_claims
from aletheia.cascade.matching import overlap_ratio
from aletheia.cascade.scoring import EvidenceClass, EvidenceItem

__all__ = ["CONFLICTING_ATTRIBUTE_KEYS", "FalsificationResult", "falsify"]

CONFLICTING_ATTRIBUTE_KEYS = ("date_of_birth", "national_id")


@dataclass(frozen=True)
class FalsificationResult:
    """The disconfirming evidence found for one candidate pair."""

    vetoes: tuple[EvidenceItem, ...]
    warnings: tuple[str, ...]
    probes_run: tuple[str, ...]
    strongest_disconfirming: str | None


def _normalized_attribute(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    return collapsed.casefold() if collapsed else None


def _dedupe_vetoes(vetoes: list[EvidenceItem]) -> tuple[EvidenceItem, ...]:
    ordered = sorted(vetoes, key=lambda item: (item.reason, item.origin))
    seen: set[tuple[str, str]] = set()
    unique: list[EvidenceItem] = []
    for item in ordered:
        key = (item.reason, item.origin)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def falsify(
    left_claims: Sequence[Claim],
    right_claims: Sequence[Claim],
    *,
    left_era: tuple[datetime, datetime] | None = None,
    right_era: tuple[datetime, datetime] | None = None,
) -> FalsificationResult:
    """Run the disconfirming probes over one claim pair."""
    probes_run: list[str] = []
    vetoes: list[EvidenceItem] = []
    warnings: list[str] = []

    probes_run.append("cross-claim veto sweep")
    for left in left_claims:
        for right in right_claims:
            if left.claim_id == right.claim_id:
                continue
            for item in compare_claims(left, right):
                if item.evidence_class is EvidenceClass.VETO:
                    vetoes.append(item)

    probes_run.append("attribute contradictions")
    for left in left_claims:
        for right in right_claims:
            if left.claim_id == right.claim_id:
                continue
            for key in CONFLICTING_ATTRIBUTE_KEYS:
                left_value = _normalized_attribute(left.attributes.get(key))
                right_value = _normalized_attribute(right.attributes.get(key))
                if left_value is None or right_value is None:
                    continue
                if left_value != right_value:
                    vetoes.append(
                        EvidenceItem(
                            evidence_class=EvidenceClass.VETO,
                            reason=f"conflicting {key}",
                            origin=pair_origin_key(left, right),
                        )
                    )

    if left_era is not None and right_era is not None:
        probes_run.append("era coherence")
        if overlap_ratio(left_era[0], left_era[1], right_era[0], right_era[1]) == 0.0:
            warnings.append(
                "disjoint activity eras "
                f"({left_era[0].isoformat()} -- {left_era[1].isoformat()} vs "
                f"{right_era[0].isoformat()} -- {right_era[1].isoformat()}): "
                "no temporal overlap (soft; platforms are left)"
            )

    unique_vetoes = _dedupe_vetoes(vetoes)
    strongest: str | None = None
    if unique_vetoes:
        first = unique_vetoes[0]
        strongest = f"{first.reason} ({first.evidence_class.value} via {first.origin})"
    elif warnings:
        strongest = warnings[0]
    return FalsificationResult(
        vetoes=unique_vetoes,
        warnings=tuple(warnings),
        probes_run=tuple(probes_run),
        strongest_disconfirming=strongest,
    )
