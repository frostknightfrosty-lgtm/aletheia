"""Blind-spot registry (P17.7).

Design of record: ``docs/PIVOT_CASCADE.md`` section 9 — "per-source known
limits (e.g., 'no public email fields') so the engine never wastes budget on
dead pivots and the report lists exactly what remains unreachable and why".

Two layers:

- :data:`KNOWN_LIMITS` — curated, code-reviewed limits, each with a citation
  to the repository document that established it. Only facts already recorded
  in this repository appear here; nothing is guessed.
- :class:`BlindSpotStore` — append-only JSONL under the data root recording
  limits observed during runs (skip records, platform walls). Local state,
  never committed.

:class:`BlindSpotRegistry` merges both for a source. This is the data the
coverage audit (P17.8) and the engine consult so dead pivots are not
re-proposed. Keys are adapter descriptor names where an adapter exists,
otherwise the source-family name used in the design document.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aletheia.core.models import utc_now

__all__ = ["KNOWN_LIMITS", "BlindSpotRegistry", "BlindSpotStore", "ObservedLimit"]

# Curated, cited limits. Every entry must trace to a document in this repo.
KNOWN_LIMITS: dict[str, tuple[str, ...]] = {
    "hibp": (
        "direct account lookups require a paid subscription; excluded by the "
        "nothing-paid rule (design section 10.2)",
    ),
    "opencorporates": (
        "non-open access paths are paid-only; only open endpoints are used "
        "(design section 10.2)",
    ),
    "onyphe": (
        "Free View is limited to the operator's own systems; excluded "
        "(design section 10.2)",
    ),
    "instaloader": (
        "unauthenticated public Instagram profile metadata only "
        "(docs/phase5/SOCIAL_GEO_IMAGE.md); platform walls (login walls, bot "
        "protection, 429s) cap this source (design section 16)",
    ),
    "followthemoney": (
        "externally blocked — Gate 7 documented exclusion: no published "
        "request contract, and the parent OpenSecrets API was discontinued "
        "2025-04-15 (docs/NOT_INTEGRATED.md)",
    ),
    "darkweb_search": (
        "Gate 6 deferral — no sub-source has a documented, verifiable request "
        "contract suitable for the composite pattern (GATES.md, Gate 6)",
    ),
}


@dataclass(frozen=True)
class ObservedLimit:
    source: str
    limitation: str
    run_id: str | None
    recorded_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "limitation": self.limitation,
            "run_id": self.run_id,
            "recorded_at": self.recorded_at,
        }


class BlindSpotStore:
    """Append-only observed limits under the data root."""

    def __init__(self, path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or utc_now

    def record(self, source: str, limitation: str, *, run_id: str | None = None) -> ObservedLimit:
        if not source or not limitation:
            raise ValueError("source and limitation must be non-empty")
        entry = ObservedLimit(
            source=source,
            limitation=limitation,
            run_id=run_id,
            recorded_at=self._clock().isoformat(),
        )
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
        return entry

    def all(self) -> list[ObservedLimit]:
        if not self.path.exists():
            return []
        entries: list[ObservedLimit] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            entries.append(
                ObservedLimit(
                    source=str(raw["source"]),
                    limitation=str(raw["limitation"]),
                    run_id=None if raw.get("run_id") is None else str(raw["run_id"]),
                    recorded_at=str(raw["recorded_at"]),
                )
            )
        return entries

    def limits_for(self, source: str) -> tuple[ObservedLimit, ...]:
        return tuple(entry for entry in self.all() if entry.source == source)


class BlindSpotRegistry:
    """Merged view of curated and observed limits, per source."""

    def __init__(self, store: BlindSpotStore | None = None) -> None:
        self.store = store

    def limits_for(self, source: str) -> tuple[str, ...]:
        """Curated limits first, then observed ones (deduplicated, in order)."""
        merged: list[str] = []
        for limitation in KNOWN_LIMITS.get(source, ()):
            if limitation not in merged:
                merged.append(limitation)
        if self.store is not None:
            for entry in self.store.limits_for(source):
                if entry.limitation not in merged:
                    merged.append(entry.limitation)
        return tuple(merged)

    def sources(self) -> tuple[str, ...]:
        """Every source with a known or observed limit, sorted."""
        names = set(KNOWN_LIMITS)
        if self.store is not None:
            names.update(entry.source for entry in self.store.all())
        return tuple(sorted(names))

    def record(self, source: str, limitation: str, *, run_id: str | None = None) -> ObservedLimit:
        if self.store is None:
            raise ValueError("registry has no BlindSpotStore to record into")
        return self.store.record(source, limitation, run_id=run_id)
