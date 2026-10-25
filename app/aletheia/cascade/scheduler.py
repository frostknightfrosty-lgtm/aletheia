"""VOI scheduler, adaptive budgets, stop policy, and resume (P17.6).

Design of record: ``docs/PIVOT_CASCADE.md`` section 8.

Priority = value of information (VOI), expected uncertainty reduction per
unit cost::

    voi = prior_probability
          * adapter_yield * pivot_rarity
          / max(cost, MIN_COST)
          * DEPTH_PENALTY ** (depth - 1)
          * freshness

- ``prior_probability`` — attribution prior of the parent hypothesis from the
  scoring/ACH layer (callers pass it explicitly, 0..1; never fabricated).
- ``adapter_yield`` — expected useful yield of the expansion, from the
  benchmark store when labeled (``phase7.benchmark``); ``DEFAULT_YIELD``
  otherwise.
- ``pivot_rarity`` — expected rarity of the identifiers the expansion should
  surface (base-rate priors layer); ``DEFAULT_RARITY`` when unknown.
- ``cost`` — planned execution cost (benchmark cost when labeled,
  ``DEFAULT_COST`` otherwise), never divides below ``MIN_COST``.
- ``DEPTH_PENALTY`` — deeper chains are worth less (reviewable constant).
- ``freshness`` — 0 while a cached observation is inside its TTL (no egress
  value: the cache answers), ramping to 1 over one further TTL
  (:func:`freshness_factor`); callers pass 1.0 when no cache covers the
  pivot. Fresh items are refused at ``push`` (recorded, not scheduled).

Adaptive budget (section 8): default depth 3, escalating to ``hard_depth``
(5) when HARD evidence has been noted *and* the run is in owner mode; under
time pressure the effective limit de-escalates by one. Per-type caps: emails
10, phones 5, names 5 (``NAME``/``PERSON_NAME``), domains 25, urls 50 (other
types uncapped). Caps count granted expansions, not claims.

Stop reasons: ``saturated`` (a full sweep added nothing above the floor),
``diminishing_returns`` (the best remaining VOI is below ``min_voi``),
``depth`` (everything left is deeper than the effective limit), ``budget``
(``max_expansions`` or every remaining type capped), ``time`` (time budget
exhausted), ``user_stop``.

Resume: :meth:`CascadeScheduler.checkpoint` / :meth:`CascadeScheduler.from_checkpoint`
carry the ordered frontier, budget usage, sweep history, stop state, and the
recorded RNG seed; pop order is deterministic (priority, then insertion
sequence). The checkpoint dict is shaped to become the run manifest's
``frontier`` / ``budget`` / ``stop_reason`` fields when the engine wires it
(section 14).

Dedup: an expansion is refused when an identical ``(seed type, value)``
candidate was already accepted (first occurrence wins; the refusal is
recorded) — request coalescing across the cache layer (section 8).
"""

from __future__ import annotations

import heapq
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aletheia.cascade.ledger import DecisionLedger
from aletheia.cascade.scoring import EvidenceClass
from aletheia.core.models import PivotCandidate, Seed, SeedType

__all__ = [
    "DEFAULT_COST",
    "DEFAULT_RARITY",
    "DEFAULT_TYPE_CAPS",
    "DEFAULT_YIELD",
    "DEPTH_PENALTY",
    "MIN_COST",
    "TIME_PRESSURE_FRACTION",
    "CascadeScheduler",
    "FrontierEntry",
    "SchedulerPolicy",
    "StopReason",
    "freshness_factor",
    "voi_score",
]

DEPTH_PENALTY = 0.6
DEFAULT_YIELD = 1.0
DEFAULT_RARITY = 0.5
DEFAULT_COST = 1.0
MIN_COST = 0.1
TIME_PRESSURE_FRACTION = 0.25

# Per-type expansion caps from section 8; types not listed are uncapped.
DEFAULT_TYPE_CAPS: dict[SeedType, int] = {
    SeedType.EMAIL: 10,
    SeedType.PHONE: 5,
    SeedType.NAME: 5,
    SeedType.PERSON_NAME: 5,
    SeedType.DOMAIN: 25,
    SeedType.URL: 50,
}


class StopReason(StrEnum):
    """Section 8 stop reasons, in the order the scheduler checks them."""

    SATURATED = "saturated"
    DIMINISHING_RETURNS = "diminishing_returns"
    DEPTH = "depth"
    BUDGET = "budget"
    TIME = "time"
    USER_STOP = "user_stop"


def freshness_factor(age_seconds: float, ttl_seconds: float) -> float:
    """Cached-value freshness: 0 inside TTL, ramping to 1 over one further TTL.

    A just-expired observation is still likely unchanged (low value); a long
    stale one is worth refreshing. A non-positive TTL means "no cache
    coverage" and returns 1.0.
    """
    if age_seconds < 0:
        raise ValueError("age_seconds must be >= 0")
    if ttl_seconds <= 0:
        return 1.0
    if age_seconds < ttl_seconds:
        return 0.0
    return min(1.0, (age_seconds - ttl_seconds) / ttl_seconds)


def voi_score(
    *,
    prior_probability: float,
    adapter_yield: float = DEFAULT_YIELD,
    pivot_rarity: float = DEFAULT_RARITY,
    cost: float = DEFAULT_COST,
    depth: int = 1,
    freshness: float = 1.0,
) -> float:
    """The section-8 VOI formula; all inputs validated, cost clamped."""
    if not 0.0 <= prior_probability <= 1.0:
        raise ValueError("prior_probability must be in [0, 1]")
    if adapter_yield < 0.0:
        raise ValueError("adapter_yield must be >= 0")
    if pivot_rarity < 0.0:
        raise ValueError("pivot_rarity must be >= 0")
    if cost < 0.0:
        raise ValueError("cost must be >= 0")
    if depth < 1:
        raise ValueError("depth must be >= 1")
    if not 0.0 <= freshness <= 1.0:
        raise ValueError("freshness must be in [0, 1]")
    return (
        prior_probability
        * adapter_yield
        * pivot_rarity
        / max(cost, MIN_COST)
        * DEPTH_PENALTY ** (depth - 1)
        * freshness
    )


@dataclass(frozen=True)
class SchedulerPolicy:
    """Budget and stop configuration for one cascade run."""

    default_depth: int = 3
    hard_depth: int = 5
    owner_mode: bool = False
    per_type_caps: Mapping[SeedType, int] = field(default_factory=lambda: dict(DEFAULT_TYPE_CAPS))
    max_expansions: int | None = None
    min_voi: float = 0.02
    time_budget_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.default_depth < 1:
            raise ValueError("default_depth must be >= 1")
        if self.hard_depth < self.default_depth:
            raise ValueError("hard_depth must be >= default_depth")
        if self.max_expansions is not None and self.max_expansions < 0:
            raise ValueError("max_expansions must be >= 0 or None")
        if self.min_voi < 0.0:
            raise ValueError("min_voi must be >= 0")
        if self.time_budget_seconds is not None and self.time_budget_seconds <= 0.0:
            raise ValueError("time_budget_seconds must be > 0 or None")
        for seed_type, cap in self.per_type_caps.items():
            if cap < 0:
                raise ValueError(f"per-type cap for {seed_type} must be >= 0")

    def cap_for(self, seed_type: SeedType) -> int | None:
        return self.per_type_caps.get(seed_type)


@dataclass(frozen=True)
class FrontierEntry:
    """One scored, schedulable expansion (a gated pivot plus its priority)."""

    candidate: PivotCandidate
    depth: int
    priority: float
    sequence: int
    decomposition: Mapping[str, float]


class CascadeScheduler:
    """Deterministic VOI-priority frontier with budgets, stops, and resume."""

    _CHECKPOINT_VERSION = 1

    def __init__(
        self,
        policy: SchedulerPolicy | None = None,
        *,
        ledger: DecisionLedger | None = None,
        clock: Callable[[], float] | None = None,
        rng_seed: int = 0,
    ) -> None:
        self.policy = policy or SchedulerPolicy()
        self.ledger = ledger
        self.rng_seed = int(rng_seed)
        self._clock = clock or time.monotonic
        self._started = self._clock()
        self._heap: list[tuple[float, int, FrontierEntry]] = []
        self._sequence = 0
        self._seen: set[tuple[SeedType, str]] = set()
        self._used: dict[SeedType, int] = {}
        self._expansions = 0
        self._passes = 0
        self._hard_seen = False
        self._saturated = False
        self._stop_reason: StopReason | None = None
        self._stop_note = ""

    # -- introspection --------------------------------------------------------

    @property
    def expansions(self) -> int:
        return self._expansions

    @property
    def passes(self) -> int:
        return self._passes

    @property
    def hard_seen(self) -> bool:
        return self._hard_seen

    @property
    def saturated(self) -> bool:
        return self._saturated

    @property
    def stop_reason(self) -> StopReason | None:
        return self._stop_reason

    @property
    def stop_note(self) -> str:
        return self._stop_note

    @property
    def frontier_size(self) -> int:
        return len(self._heap)

    def used_for(self, seed_type: SeedType) -> int:
        return self._used.get(seed_type, 0)

    def mark_seen(self, seed: Seed) -> None:
        """Mark a root seed as already queried before pivot scheduling begins."""
        self._seen.add((seed.type, seed.value))

    def elapsed_seconds(self) -> float:
        return max(0.0, self._clock() - self._started)

    def pending(self) -> tuple[FrontierEntry, ...]:
        """The frontier in pop order (deterministic)."""
        return tuple(entry for _, _, entry in sorted(self._heap))

    # -- engine signals -------------------------------------------------------

    def note_evidence(self, evidence_class: EvidenceClass) -> None:
        """Record arriving evidence; HARD evidence enables depth escalation."""
        if evidence_class is EvidenceClass.HARD:
            self._hard_seen = True

    def note_pass(self, *, added_above_floor: int) -> None:
        """Record one completed sweep of the frontier (design section 8)."""
        if added_above_floor < 0:
            raise ValueError("added_above_floor must be >= 0")
        self._passes += 1
        self._record(
            "sweep",
            {
                "pass": self._passes,
                "added_above_floor": added_above_floor,
                "expansions": self._expansions,
            },
        )
        if added_above_floor == 0:
            self._saturated = True

    def stop(self, reason: StopReason, *, note: str = "") -> bool:
        """Latch an explicit stop; returns False when a stop already exists."""
        if self._stop_reason is not None:
            return False
        self._stop_reason = reason
        self._stop_note = note
        self._record(
            "stop",
            {
                "reason": reason.value,
                "note": note,
                "expansions": self._expansions,
                "passes": self._passes,
            },
        )
        return True

    # -- depth/budget policy --------------------------------------------------

    def effective_depth_limit(self) -> int:
        base = self.policy.hard_depth if (self.policy.owner_mode and self._hard_seen) else self.policy.default_depth
        if self.time_pressure():
            return max(1, base - 1)
        return base

    def time_pressure(self) -> bool:
        budget = self.policy.time_budget_seconds
        if budget is None:
            return False
        return self.elapsed_seconds() >= budget * (1.0 - TIME_PRESSURE_FRACTION)

    def should_stop(self) -> StopReason | None:
        """The current stop reason, or None when work should continue."""
        if self._stop_reason is not None:
            return self._stop_reason
        budget = self.policy.time_budget_seconds
        if budget is not None and self.elapsed_seconds() >= budget:
            return StopReason.TIME
        if self._saturated:
            return StopReason.SATURATED
        if self.policy.max_expansions is not None and self._expansions >= self.policy.max_expansions:
            return StopReason.BUDGET
        if not self._heap:
            return None
        limit = self.effective_depth_limit()
        if all(entry.depth > limit for _, _, entry in self._heap):
            return StopReason.DEPTH
        if all(
            (cap := self.policy.cap_for(entry.candidate.seed.type)) is not None
            and self.used_for(entry.candidate.seed.type) >= cap
            for _, _, entry in self._heap
        ):
            return StopReason.BUDGET
        if -self._heap[0][0] < self.policy.min_voi:
            return StopReason.DIMINISHING_RETURNS
        return None

    # -- frontier -------------------------------------------------------------

    def push(
        self,
        candidate: PivotCandidate,
        *,
        prior_probability: float,
        adapter_yield: float = DEFAULT_YIELD,
        pivot_rarity: float = DEFAULT_RARITY,
        cost: float = DEFAULT_COST,
        depth: int = 1,
        freshness: float = 1.0,
    ) -> FrontierEntry | None:
        """Score and enqueue one gated pivot; refusals are recorded, not silent."""
        if depth < 1:
            raise ValueError("depth must be >= 1")
        if not 0.0 <= freshness <= 1.0:
            raise ValueError("freshness must be in [0, 1]")
        if depth > self.policy.hard_depth:
            self._record("pivot_refused", self._refusal(candidate, depth, "beyond_hard_depth", None))
            return None
        key = (candidate.seed.type, candidate.seed.value)
        if key in self._seen:
            self._record("pivot_refused", self._refusal(candidate, depth, "duplicate", None))
            return None
        if freshness <= 0.0:
            self._record("pivot_refused", self._refusal(candidate, depth, "fresh_cache", None))
            return None
        priority = voi_score(
            prior_probability=prior_probability,
            adapter_yield=adapter_yield,
            pivot_rarity=pivot_rarity,
            cost=cost,
            depth=depth,
            freshness=freshness,
        )
        decomposition = {
            "prior_probability": float(prior_probability),
            "adapter_yield": float(adapter_yield),
            "pivot_rarity": float(pivot_rarity),
            "cost": float(cost),
            "depth_penalty": DEPTH_PENALTY ** (depth - 1),
            "freshness": float(freshness),
            "priority": priority,
        }
        entry = FrontierEntry(
            candidate=candidate,
            depth=depth,
            priority=priority,
            sequence=self._sequence,
            decomposition=decomposition,
        )
        heapq.heappush(self._heap, (-priority, self._sequence, entry))
        self._seen.add(key)
        self._sequence += 1
        self._record(
            "pivot_proposed",
            {
                "pivot_id": str(candidate.pivot_id),
                "seed_type": candidate.seed.type.value,
                "seed_value": candidate.seed.value,
                "depth": depth,
                "gate": candidate.gate.value,
                "priority": priority,
                "reason": candidate.reason,
                "decomposition": decomposition,
            },
        )
        return entry

    def pop(self) -> FrontierEntry | None:
        """Take the next expansion the budget and depth policy allow.

        Entries refused mid-scan (depth, per-type cap) are dropped and
        recorded; a later escalation does not resurrect them — the engine
        re-pushes if the sweep still wants them.
        """
        if self.should_stop() is not None:
            return None
        limit = self.effective_depth_limit()
        while self._heap:
            _, _, entry = heapq.heappop(self._heap)
            if entry.depth > limit:
                self._record("pivot_refused", self._refusal(entry.candidate, entry.depth, "depth", limit))
                continue
            cap = self.policy.cap_for(entry.candidate.seed.type)
            used = self.used_for(entry.candidate.seed.type)
            if cap is not None and used >= cap:
                self._record("pivot_refused", self._refusal(entry.candidate, entry.depth, "budget", cap))
                continue
            self._used[entry.candidate.seed.type] = used + 1
            self._expansions += 1
            self._record(
                "pivot_granted",
                {
                    "pivot_id": str(entry.candidate.pivot_id),
                    "seed_type": entry.candidate.seed.type.value,
                    "seed_value": entry.candidate.seed.value,
                    "depth": entry.depth,
                    "priority": entry.priority,
                    "expansion_number": self._expansions,
                    "budget_used": self._used[entry.candidate.seed.type],
                },
            )
            return entry
        return None

    # -- resume ---------------------------------------------------------------

    def checkpoint(self) -> dict[str, Any]:
        """A JSON-safe resume state (frontier order, budgets, stops, seed)."""
        return {
            "checkpoint_version": self._CHECKPOINT_VERSION,
            "rng_seed": self.rng_seed,
            "sequence": self._sequence,
            "expansions": self._expansions,
            "passes": self._passes,
            "hard_seen": self._hard_seen,
            "saturated": self._saturated,
            "stop_reason": self._stop_reason.value if self._stop_reason is not None else None,
            "stop_note": self._stop_note,
            "used_by_type": {seed_type.value: count for seed_type, count in sorted(self._used.items())},
            "seen": [
                {"type": seed_type.value, "value": value}
                for seed_type, value in sorted(
                    self._seen, key=lambda item: (item[0].value, item[1])
                )
            ],
            "frontier": [
                {
                    "candidate": entry.candidate.model_dump(mode="json"),
                    "depth": entry.depth,
                    "priority": entry.priority,
                    "sequence": entry.sequence,
                    "decomposition": dict(entry.decomposition),
                }
                for entry in self.pending()
            ],
        }

    @classmethod
    def from_checkpoint(
        cls,
        state: Mapping[str, Any],
        *,
        policy: SchedulerPolicy | None = None,
        ledger: DecisionLedger | None = None,
        clock: Callable[[], float] | None = None,
    ) -> "CascadeScheduler":
        """Rebuild a scheduler whose remaining work matches the checkpoint."""
        version = int(state.get("checkpoint_version", -1))
        if version != cls._CHECKPOINT_VERSION:
            raise ValueError(f"unsupported checkpoint version: {version}")
        scheduler = cls(
            policy,
            ledger=ledger,
            clock=clock,
            rng_seed=int(state.get("rng_seed", 0)),
        )
        scheduler._seen.update(
            (SeedType(item["type"]), str(item["value"]))
            for item in state.get("seen", [])
        )
        highest_sequence = -1
        for raw in state.get("frontier", []):
            candidate = PivotCandidate.model_validate(raw["candidate"])
            entry = FrontierEntry(
                candidate=candidate,
                depth=int(raw["depth"]),
                priority=float(raw["priority"]),
                sequence=int(raw["sequence"]),
                decomposition=dict(raw.get("decomposition", {})),
            )
            heapq.heappush(scheduler._heap, (-entry.priority, entry.sequence, entry))
            scheduler._seen.add((candidate.seed.type, candidate.seed.value))
            highest_sequence = max(highest_sequence, entry.sequence)
        scheduler._sequence = max(int(state.get("sequence", 0)), highest_sequence + 1)
        scheduler._expansions = int(state.get("expansions", 0))
        scheduler._passes = int(state.get("passes", 0))
        scheduler._hard_seen = bool(state.get("hard_seen", False))
        scheduler._saturated = bool(state.get("saturated", False))
        raw_stop = state.get("stop_reason")
        scheduler._stop_reason = StopReason(raw_stop) if raw_stop else None
        scheduler._stop_note = str(state.get("stop_note", ""))
        scheduler._used = {
            SeedType(seed_type): int(count) for seed_type, count in state.get("used_by_type", {}).items()
        }
        return scheduler

    # -- internals ------------------------------------------------------------

    def _record(self, kind: str, payload: Mapping[str, Any]) -> None:
        if self.ledger is not None:
            self.ledger.append(kind, payload)

    @staticmethod
    def _refusal(
        candidate: PivotCandidate,
        depth: int,
        reason: str,
        limit: int | None,
    ) -> dict[str, Any]:
        return {
            "pivot_id": str(candidate.pivot_id),
            "seed_type": candidate.seed.type.value,
            "seed_value": candidate.seed.value,
            "depth": depth,
            "reason": reason,
            "limit": limit,
        }
