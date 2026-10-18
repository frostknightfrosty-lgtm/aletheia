"""Deterministic cascade engine over an injectable observer (Phase 17, P17.9).

Design of record: ``docs/PIVOT_CASCADE.md`` sections 4-8. The engine drives
one investigation: seeded claims -> gated pivot extraction (section 7) ->
VOI-scheduled expansions (section 8, P17.6) -> observations -> claim
normalization (P17.3) -> blocking + evidence (P17.4) -> falsification and ACH
(P17.5) -> confirmed merges — recording every hop in a parent-linked trail and
every decision in the hash-chained ledger, and stopping on the section-8
reasons (saturated | diminishing_returns | depth | budget | time | user_stop).

The observer is the boundary between determinism and the network::

    observer: Callable[[Seed], Observation]

CI and the synthetic-world suites inject pure fixture observers (no I/O, no
network); the live wiring injects adapter queries. Given the same root
claims, observer, and policy, a run performs the same sequence of expansions
and produces the same trail digest. Claim UUIDs are random, so the golden
digest covers the hops (``aletheia.cascade.trail.trail_digest``), not the ids.

Subject model (v1, documented composition reading of sections 5-6.3):

- The **anchor claims** (root claims) came from the seed resolution the
  investigation authorized, so they are definitionally the subject's. Later
  accepted merges extend the **subject claim set**. Anchors are registered on
  the merge graph, not merged through it; only confirmed merges create edges.
- Claims are kept **per origin**: the same adapter echoing the same value for
  the same seed slot is one origin and never counts twice (the P17.4
  independence rule), while an independent adapter observing the same value
  is a distinct origin — that is what makes HARD/STRONG evidence reachable at
  all, and it is the intended reading of "two echoes of the same observation
  never count twice".
- Arriving claims are compared against the subject set only through the
  P17.3 **blocking** (strong-key pairs) — never O(n^2). A claim merges only
  when the P17.4 tier is ``confirmed`` **and** ACH (P17.5) leaves
  ``H_subject`` leading by the margin; everything else is recorded as a
  candidate with its reason. Vetoes always win: falsification runs first and
  a veto excludes the claim before any evidence is summed.
- Pivot gating follows section 7 on the claim's **effective tier**: merged
  claims gate everything; unmerged candidates gate structural seeds at
  ``probable`` but are capped below ``confirmed`` (personal identifiers
  require a confirmed origin cluster, so an unmerged confirmed guess is
  capped at probable for spawning). Excluded and below-probable claims spawn
  nothing; every gate refusal is recorded (``pivot_gated``), never silent.
- v1 reachability, stated plainly: with identical-key blocking, the evidence
  table's reachable rows are (a) identical values from independent origins
  (HARD/STRONG) and (b) domain-bridged pairs (MEDIUM/WEAK for
  domain/host/url claims). Name-class support and similarity-only rows need a
  shared block to pair and therefore fire in v1 only for conflicting names,
  through the falsification sweep. This is a property of the P17.3 blocking
  policy (weak keys must not chain), not an accident; the synthetic worlds in
  ``tests/test_cascade_engine.py`` pin exactly what is and is not reachable.

Saturation floor (provisional reading of section 8 "no claim above the
floor"): v1 has no calibrated claim confidence, so the floor counts new
information — a wave adds a claim when its ``(type, value)`` is new to the
run, or when a repeated value from an independent origin was accepted as a
merge. Everything else in a wave is still processed (echoes contribute
evidence); only the saturation counter ignores it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from aletheia.cascade.ach import assess_hypotheses
from aletheia.cascade.claims import (
    Claim,
    block_claims,
    claim_from_finding,
    claim_origin_key,
    dedupe_claims,
)
from aletheia.cascade.evidence import compare_claims
from aletheia.cascade.extractors import extract_pivots
from aletheia.cascade.falsify import falsify
from aletheia.cascade.ledger import DecisionLedger
from aletheia.cascade.merge_graph import MergeGraph
from aletheia.cascade.priors import handle_prior_log_odds
from aletheia.cascade.scheduler import CascadeScheduler, SchedulerPolicy, StopReason
from aletheia.cascade.scoring import score_evidence, tier_for
from aletheia.cascade.trail import TrailHop
from aletheia.core.models import (
    ClusterDecision,
    EntityType,
    Finding,
    Hypothesis,
    IdentityTier,
    Seed,
    SeedType,
)

__all__ = ["CandidateCase", "CascadeEngine", "CascadeResult", "Observation"]

# Provisional v1 priors for the VOI push: username seeds use the P17.4 handle
# entropy prior (mapped through the logistic), everything else is uninformative.
_DEFAULT_PRIOR_PROBABILITY = 0.5

_TIER_RANK: dict[IdentityTier | None, int] = {
    IdentityTier.EXCLUDED: -1,
    None: 0,
    IdentityTier.POSSIBLE: 1,
    IdentityTier.PROBABLE: 2,
    IdentityTier.CONFIRMED: 3,
}


@dataclass(frozen=True)
class Observation:
    """One observer answer: findings, or a recorded block (never retried)."""

    findings: tuple[Finding, ...] = ()
    blocked_reason: str = ""


Observer = Callable[[Seed], Observation]


@dataclass(frozen=True)
class CandidateCase:
    """One observed claim with its decided outcome."""

    claim: Claim
    tier: IdentityTier | None
    accepted: bool
    reason: str
    ach_surviving: Hypothesis | None
    veto: str | None


@dataclass
class CascadeResult:
    """Everything one engine run produced (all deterministic per input)."""

    subject_claims: tuple[Claim, ...]
    candidates: tuple[CandidateCase, ...]
    decisions: tuple[ClusterDecision, ...]
    hops: tuple[TrailHop, ...]
    ledger: DecisionLedger
    graph: MergeGraph
    stop_reason: StopReason
    stop_note: str
    expansions: int
    passes: int
    checkpoint: dict[str, Any]


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


class CascadeEngine:
    """The cascade loop; performs no I/O — every observation is injected."""

    def __init__(
        self,
        observer: Observer,
        *,
        policy: SchedulerPolicy | None = None,
        ledger: DecisionLedger | None = None,
        rng_seed: int = 0,
        max_waves: int = 64,
    ) -> None:
        if max_waves < 1:
            raise ValueError("max_waves must be >= 1")
        self._observer = observer
        self._policy = policy or SchedulerPolicy()
        self._ledger = ledger
        self._rng_seed = int(rng_seed)
        self._max_waves = max_waves

    # -- VOI priors -----------------------------------------------------------

    @staticmethod
    def _prior_probability(seed: Seed) -> float:
        if seed.type is SeedType.USERNAME:
            log_odds = handle_prior_log_odds(seed.value).log_odds
            return _sigmoid(log_odds)
        return _DEFAULT_PRIOR_PROBABILITY

    # -- the run --------------------------------------------------------------

    def run(self, root_claims: Sequence[Claim], *, subject_label: str = "subject") -> CascadeResult:
        anchors = dedupe_claims(root_claims)
        if not anchors:
            raise ValueError("engine needs at least one root claim")
        ledger = self._ledger if self._ledger is not None else DecisionLedger()
        scheduler = CascadeScheduler(self._policy, ledger=ledger, rng_seed=self._rng_seed)
        graph = MergeGraph()
        subject_node = str(uuid5(NAMESPACE_URL, f"aletheia:subject:{subject_label}"))
        graph.find(subject_node)

        subject_claims: list[Claim] = list(anchors)
        known_values: set[tuple[EntityType, str]] = {(c.type, c.value) for c in anchors}
        processed: set[tuple[str, EntityType, str]] = set()
        finding_hop: dict[UUID, str] = {}
        hops: list[TrailHop] = []
        decisions: list[ClusterDecision] = []
        candidates: list[CandidateCase] = []
        wave_added = 0
        waves = 0

        for anchor in anchors:
            self._pump(
                anchor,
                origin_tier=IdentityTier.CONFIRMED,
                depth=1,
                scheduler=scheduler,
                ledger=ledger,
            )

        while True:
            if scheduler.should_stop() is not None:
                break
            if waves >= self._max_waves:
                scheduler.stop(
                    StopReason.BUDGET, note=f"engine wave guard ({self._max_waves} waves)"
                )
                break
            entry = scheduler.pop()
            if entry is None:
                scheduler.note_pass(added_above_floor=wave_added)
                wave_added = 0
                waves += 1
                continue

            hop_id = f"hop-{len(hops) + 1:04d}"
            parent_hop_id = (
                finding_hop.get(entry.candidate.parent_finding_id)
                if entry.candidate.parent_finding_id is not None
                else None
            )
            observation = self._observer(entry.candidate.seed)
            if observation.blocked_reason:
                hops.append(
                    TrailHop(
                        hop_id=hop_id,
                        parent_hop_id=parent_hop_id,
                        seed_type=entry.candidate.seed.type,
                        seed_value=entry.candidate.seed.value,
                        depth=entry.depth,
                        outcome="blocked",
                        claims_found=0,
                        reason=observation.blocked_reason,
                    )
                )
                continue

            processed_here = 0
            for finding in observation.findings:
                finding_hop.setdefault(finding.finding_id, hop_id)
                claim = claim_from_finding(finding)
                key = (claim_origin_key(claim), claim.type, claim.value)
                if key in processed:
                    continue
                processed.add(key)
                processed_here += 1
                value_key = (claim.type, claim.value)
                novel_value = value_key not in known_values
                known_values.add(value_key)
                accepted = self._process_claim(
                    claim,
                    subject_claims=subject_claims,
                    subject_node=subject_node,
                    graph=graph,
                    scheduler=scheduler,
                    ledger=ledger,
                    depth=entry.depth + 1,
                    decisions=decisions,
                    candidates=candidates,
                )
                if novel_value or accepted:
                    wave_added += 1

            hops.append(
                TrailHop(
                    hop_id=hop_id,
                    parent_hop_id=parent_hop_id,
                    seed_type=entry.candidate.seed.type,
                    seed_value=entry.candidate.seed.value,
                    depth=entry.depth,
                    outcome="expanded" if processed_here else "empty",
                    claims_found=processed_here,
                    reason=entry.candidate.reason,
                )
            )

        stop_reason = scheduler.should_stop()
        if stop_reason is not None:
            scheduler.stop(stop_reason, note="engine ended run")
        final_reason = scheduler.stop_reason or StopReason.SATURATED
        ok, detail = ledger.verify()
        if not ok:
            raise RuntimeError(f"engine ledger failed verification: {detail}")
        return CascadeResult(
            subject_claims=tuple(subject_claims),
            candidates=tuple(candidates),
            decisions=tuple(decisions),
            hops=tuple(hops),
            ledger=ledger,
            graph=graph,
            stop_reason=final_reason,
            stop_note=scheduler.stop_note,
            expansions=scheduler.expansions,
            passes=scheduler.passes,
            checkpoint=scheduler.checkpoint(),
        )

    # -- internals ------------------------------------------------------------

    def _pump(
        self,
        claim: Claim,
        *,
        origin_tier: IdentityTier | None,
        depth: int,
        scheduler: CascadeScheduler,
        ledger: DecisionLedger,
    ) -> None:
        for candidate in extract_pivots(claim):
            if _TIER_RANK[origin_tier] < _TIER_RANK[candidate.gate]:
                ledger.append(
                    "pivot_gated",
                    {
                        "seed_type": candidate.seed.type.value,
                        "seed_value": candidate.seed.value,
                        "gate": candidate.gate.value,
                        "origin_tier": origin_tier.value if origin_tier is not None else None,
                        "reason": (
                            "personal identifiers require a confirmed origin cluster"
                            if candidate.gate is IdentityTier.CONFIRMED
                            else "structural seeds require a probable origin cluster"
                        ),
                    },
                )
                continue
            scheduler.push(
                candidate,
                prior_probability=self._prior_probability(candidate.seed),
                depth=depth,
            )

    def _process_claim(
        self,
        claim: Claim,
        *,
        subject_claims: list[Claim],
        subject_node: str,
        graph: MergeGraph,
        scheduler: CascadeScheduler,
        ledger: DecisionLedger,
        depth: int,
        decisions: list[ClusterDecision],
        candidates: list[CandidateCase],
    ) -> bool:
        """Falsify, compare, decide, merge, and pump one arriving claim.

        Returns True when the claim was accepted into the subject cluster.
        """
        falsification = falsify([claim], subject_claims)
        for item in falsification.vetoes:
            scheduler.note_evidence(item.evidence_class)
        if falsification.vetoes:
            strongest = falsification.strongest_disconfirming or "veto"
            graph.conflict(subject_node, str(claim.claim_id), reason=strongest)
            decision = ClusterDecision(
                entity_ids=[UUID(subject_node), claim.claim_id],
                tier=IdentityTier.EXCLUDED,
                accepted=False,
                conflict=strongest,
                reason="falsification veto",
            )
            decisions.append(decision)
            candidates.append(
                CandidateCase(
                    claim=claim,
                    tier=IdentityTier.EXCLUDED,
                    accepted=False,
                    reason="falsification veto",
                    ach_surviving=None,
                    veto=strongest,
                )
            )
            ledger.append(
                "falsify",
                {
                    "claim_id": str(claim.claim_id),
                    "claim_type": claim.type.value,
                    "claim_value": claim.value,
                    "source_adapter": claim.source_adapter,
                    "strongest_disconfirming": strongest,
                    "probes": list(falsification.probes_run),
                    "vetoes": [item.reason for item in falsification.vetoes],
                },
            )
            return False

        combined = [*subject_claims, claim]
        by_id = {candidate.claim_id: candidate for candidate in combined}
        items = []
        for left_id, right_id in block_claims(combined).pairs:
            if claim.claim_id not in (left_id, right_id):
                continue
            items.extend(compare_claims(by_id[left_id], by_id[right_id]))
        for item in items:
            scheduler.note_evidence(item.evidence_class)

        tier_result = tier_for(items)
        ach = assess_hypotheses(items)
        score_result = score_evidence(items)
        accepted = tier_result.tier is IdentityTier.CONFIRMED and ach.surviving is Hypothesis.SUBJECT
        if accepted:
            reason = "confirmed merge"
        elif tier_result.tier is None:
            reason = "no supporting evidence against the subject set"
        else:
            reason = f"candidate ({tier_result.tier.value})"
        decision = ClusterDecision(
            entity_ids=[UUID(subject_node), claim.claim_id],
            tier=tier_result.tier,
            accepted=accepted,
            score=score_result.log_lr_total,
            assessments=list(ach.assessments),
            reason=reason,
        )
        decisions.append(decision)
        candidates.append(
            CandidateCase(
                claim=claim,
                tier=tier_result.tier,
                accepted=accepted,
                reason=reason,
                ach_surviving=ach.surviving,
                veto=None,
            )
        )
        ledger.append(
            "merge",
            {
                "claim_id": str(claim.claim_id),
                "claim_type": claim.type.value,
                "claim_value": claim.value,
                "source_adapter": claim.source_adapter,
                "tier": tier_result.tier.value if tier_result.tier is not None else None,
                "accepted": accepted,
                "score": score_result.log_lr_total,
                "ach_surviving": ach.surviving.value if ach.surviving is not None else None,
                "ach_rationale": ach.rationale,
                "evidence": [item.reason for item in items],
                "capped_by_review_gate": tier_result.capped_by_review_gate,
                "capped_by_low_grade": tier_result.capped_by_low_grade,
            },
        )

        if accepted:
            merged, _ = graph.attempt_merge(decision)
            if merged:
                subject_claims.append(claim)
        effective = (
            IdentityTier.CONFIRMED
            if accepted
            else (
                IdentityTier.PROBABLE
                if _TIER_RANK[tier_result.tier] >= _TIER_RANK[IdentityTier.PROBABLE]
                else tier_result.tier
            )
        )
        self._pump(claim, origin_tier=effective, depth=depth, scheduler=scheduler, ledger=ledger)
        return accepted
