"""Append-only, replayable decision ledger (Phase 17, P17.6).

Design of record: ``docs/PIVOT_CASCADE.md`` section 8 — "every pivot decision
(claim, gate, score, priority, budget) is logged and replayable (``cascade
review mode``)"; section 12 — score decomposition per claim. The ledger is
the cascade engine's own decision log: JSON-safe, sequence-numbered, and
hash-chained (each record carries the SHA-256 of its canonical payload plus
the previous record's hash), so an edited or reordered ledger is detectable
on :meth:`DecisionLedger.verify`. It does not replace the run audit chain
(``AUDIT.jsonl``, ``core/chain.py``), which stays authoritative for
adapter-level events.

Kinds written by the P17.6 scheduler: ``pivot_proposed``, ``pivot_granted``,
``pivot_refused``, ``sweep``, ``stop``. Kinds are open strings so later
steps (merge / veto decisions) extend without a schema break.

Honest limits: the chain is tamper-evidence for the local ledger, not a
signature — anyone who can rewrite the file can also recompute the hashes;
the run audit chain remains the anchored record. Replay re-prints recorded
decisions; it never re-executes adapters.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aletheia.core.chain import GENESIS_HASH
from aletheia.core.models import utc_now

__all__ = ["DecisionLedger", "LedgerEntry"]

_RESERVED_PAYLOAD_FIELDS = ("sequence", "kind", "recorded_at", "prev_hash", "hash")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class LedgerEntry:
    """One recorded decision; immutable and directly serializable."""

    sequence: int
    kind: str
    payload: Mapping[str, Any]
    recorded_at: str
    prev_hash: str
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "payload": dict(self.payload),
            "recorded_at": self.recorded_at,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


class DecisionLedger:
    """Ordered, hash-chained decision log with replay support."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or utc_now
        self._entries: list[LedgerEntry] = []

    # -- writing --------------------------------------------------------------

    def append(self, kind: str, payload: Mapping[str, Any] | None = None) -> LedgerEntry:
        """Append one decision; returns the sealed entry."""
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("ledger kind must be a non-empty string")
        body = dict(payload or {})
        reserved = sorted(set(body) & set(_RESERVED_PAYLOAD_FIELDS))
        if reserved:
            raise ValueError(f"ledger payload must not contain reserved fields: {', '.join(reserved)}")
        try:
            json.dumps(body, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("ledger payload must be JSON-serializable") from exc
        unhashed = {
            "sequence": len(self._entries) + 1,
            "kind": kind,
            "payload": body,
            "recorded_at": self._clock().isoformat(),
            "prev_hash": self._entries[-1].hash if self._entries else GENESIS_HASH,
        }
        entry = LedgerEntry(hash=hashlib.sha256(_canonical(unhashed)).hexdigest(), **unhashed)
        self._entries.append(entry)
        return entry

    # -- reading --------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def replay(self, *, kinds: Iterable[str] | None = None) -> Iterator[LedgerEntry]:
        """Iterate recorded decisions in order, optionally filtered by kind."""
        wanted = set(kinds) if kinds is not None else None
        return (entry for entry in self._entries if wanted is None or entry.kind in wanted)

    def verify(self) -> tuple[bool, str]:
        """Recompute the chain; returns ``(ok, detail)``."""
        previous = GENESIS_HASH
        for index, entry in enumerate(self._entries, start=1):
            if entry.sequence != index:
                return False, f"sequence break at position {index} (recorded {entry.sequence})"
            if entry.prev_hash != previous:
                return False, f"prev_hash break at sequence {entry.sequence}"
            unhashed = {
                "sequence": entry.sequence,
                "kind": entry.kind,
                "payload": dict(entry.payload),
                "recorded_at": entry.recorded_at,
                "prev_hash": entry.prev_hash,
            }
            expected = hashlib.sha256(_canonical(unhashed)).hexdigest()
            if entry.hash != expected:
                return False, f"hash mismatch at sequence {entry.sequence}"
            previous = entry.hash
        return True, f"{len(self._entries)} entries verified"

    # -- serialization --------------------------------------------------------

    def to_dicts(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]

    @classmethod
    def from_dicts(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        clock: Callable[[], datetime] | None = None,
        verify: bool = True,
    ) -> "DecisionLedger":
        """Rebuild a ledger from serialized records.

        With ``verify=True`` (default) a broken chain raises ``ValueError``;
        pass ``verify=False`` to load for a :meth:`verify` report.
        """
        ledger = cls(clock=clock)
        for raw in records:
            entry = LedgerEntry(
                sequence=int(raw["sequence"]),
                kind=str(raw["kind"]),
                payload=dict(raw["payload"]),
                recorded_at=str(raw["recorded_at"]),
                prev_hash=str(raw["prev_hash"]),
                hash=str(raw["hash"]),
            )
            ledger._entries.append(entry)
        if verify:
            ok, detail = ledger.verify()
            if not ok:
                raise ValueError(f"ledger does not verify: {detail}")
        return ledger
