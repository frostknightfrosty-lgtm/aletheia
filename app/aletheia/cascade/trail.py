"""Parent-linked cascade trail and its regression digest (P17.8).

Design of record: ``docs/PIVOT_CASCADE.md`` section 12 — ``cascade_trail.json``
("every hop, parent-linked") — and section 13 — the golden cascade run:
"fixed fixture => stable trail hash".

A hop is one pivot decision with its outcome:

- ``hop_id``: stable identifier supplied by the engine (unique in the trail),
- ``parent_hop_id``: the hop whose claims produced this pivot (``None`` at the
  roots),
- ``seed_type`` / ``seed_value``: the pivot exercise that was attempted,
- ``depth``: pivot-chain depth (>= 1),
- ``outcome``: ``expanded`` | ``empty`` | ``blocked`` | ``refused`` |
  ``skipped``,
- ``claims_found``: claims accepted above the floor (>= 0),
- ``reason``: required for ``blocked`` / ``refused`` / ``skipped``.

:func:`build_trail` validates uniqueness, the vocabulary, reason discipline,
parent links, and acyclicity, then serializes deterministically (sorted by
``(depth, hop_id)``). :func:`trail_digest` is the SHA-256 of the canonical
hops list — the golden-run regression hash; it deliberately covers only the
hops, so two runs of the same fixture digest identically regardless of run
identity.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from aletheia.core.models import SeedType

__all__ = ["TRAIL_OUTCOMES", "TrailError", "TrailHop", "build_trail", "trail_digest"]

TRAIL_OUTCOMES = ("expanded", "empty", "blocked", "refused", "skipped")
_REASON_REQUIRED = frozenset({"blocked", "refused", "skipped"})


class TrailError(ValueError):
    """Raised for a malformed trail (bad hop, broken link, or cycle)."""


@dataclass(frozen=True)
class TrailHop:
    hop_id: str
    seed_type: SeedType
    seed_value: str
    depth: int
    outcome: str
    parent_hop_id: str | None = None
    claims_found: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hop_id": self.hop_id,
            "parent_hop_id": self.parent_hop_id,
            "seed_type": self.seed_type.value,
            "seed_value": self.seed_value,
            "depth": self.depth,
            "outcome": self.outcome,
            "claims_found": self.claims_found,
            "reason": self.reason,
        }


def build_trail(
    hops: Sequence[TrailHop] | Iterable[TrailHop],
    *,
    run_id: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Validate and serialize a parent-linked trail, deterministically."""
    resolved = list(hops)
    seen: dict[str, TrailHop] = {}
    for hop in resolved:
        if not hop.hop_id:
            raise TrailError("hop_id must be non-empty")
        if hop.hop_id in seen:
            raise TrailError(f"duplicate hop_id: {hop.hop_id}")
        if not hop.seed_value:
            raise TrailError(f"hop {hop.hop_id}: seed_value must be non-empty")
        if hop.depth < 1:
            raise TrailError(f"hop {hop.hop_id}: depth must be >= 1")
        if hop.outcome not in TRAIL_OUTCOMES:
            raise TrailError(f"hop {hop.hop_id}: unknown outcome {hop.outcome!r}")
        if hop.claims_found < 0:
            raise TrailError(f"hop {hop.hop_id}: claims_found must be >= 0")
        if hop.outcome in _REASON_REQUIRED and not hop.reason:
            raise TrailError(f"hop {hop.hop_id}: outcome {hop.outcome!r} requires a reason")
        seen[hop.hop_id] = hop
    for hop in resolved:
        if hop.parent_hop_id is not None and hop.parent_hop_id not in seen:
            raise TrailError(f"hop {hop.hop_id}: unknown parent {hop.parent_hop_id}")
        cursor = hop
        walked = 0
        while cursor.parent_hop_id is not None:
            cursor = seen[cursor.parent_hop_id]
            walked += 1
            if walked > len(seen):
                raise TrailError(f"cycle detected at hop {hop.hop_id}")
    ordered = sorted(resolved, key=lambda hop: (hop.depth, hop.hop_id))
    return {
        "trail_version": 1,
        "run_id": run_id,
        "case_id": case_id,
        "hops": [hop.to_dict() for hop in ordered],
    }


def trail_digest(trail: dict[str, Any]) -> str:
    """SHA-256 over the canonical hops list (run identity excluded)."""
    canonical = json.dumps(
        {"hops": trail.get("hops", [])},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
