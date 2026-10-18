"""Confirmation label store feeding the calibrator (P17.7).

Design of record: ``docs/PIVOT_CASCADE.md`` section 9 — "confirmations persist
under the data root (never committed); feeds ``core/calibration.py`` (Platt /
isotonic)" — and section 12 — the confirm fast-lane (mine / not-mine / unsure
per cluster): "unsure stays a candidate; confirmations become calibration
labels".

Storage: append-only JSONL at the path given (``<data_root>/labels.jsonl`` by
convention). The latest label per ``(case_id, cluster_id)`` wins in
:meth:`LabelStore.resolved`; nothing is deleted, so the audit keeps every
call. ``training_pairs()`` yields ``(score, label)`` pairs for
``core/calibration.py``: mine -> 1, not_mine -> 0; unsure is excluded, and a
label with no recorded score is excluded — the calibrator is never fed a
fabricated score.

Honest limits: labels are operator input and are only as good as the
operator's call; this store does not verify identity claims itself, and it
never records a label the owner did not actually confirm.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from aletheia.core.models import utc_now

__all__ = ["ConfirmLabel", "LabelRecord", "LabelStore"]


class ConfirmLabel(StrEnum):
    """The section-12 fast-lane confirmations."""

    MINE = "mine"
    NOT_MINE = "not_mine"
    UNSURE = "unsure"


@dataclass(frozen=True)
class LabelRecord:
    case_id: str
    cluster_id: str
    label: ConfirmLabel
    score: float | None
    note: str
    recorded_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "cluster_id": self.cluster_id,
            "label": self.label.value,
            "score": self.score,
            "note": self.note,
            "recorded_at": self.recorded_at,
        }


class LabelStore:
    """Append-only confirmation labels under the data root."""

    def __init__(self, path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or utc_now

    def add(
        self,
        *,
        case_id: str,
        cluster_id: str,
        label: ConfirmLabel | str,
        score: float | None = None,
        note: str = "",
    ) -> LabelRecord:
        if not case_id or not cluster_id:
            raise ValueError("case_id and cluster_id must be non-empty")
        try:
            resolved_label = ConfirmLabel(str(label))
        except ValueError as exc:
            known = ", ".join(member.value for member in ConfirmLabel)
            raise ValueError(f"unknown label {label!r}; known: {known}") from exc
        record = LabelRecord(
            case_id=case_id,
            cluster_id=cluster_id,
            label=resolved_label,
            score=None if score is None else float(score),
            note=note,
            recorded_at=self._clock().isoformat(),
        )
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        return record

    # -- reading --------------------------------------------------------------

    def all(self) -> list[LabelRecord]:
        if not self.path.exists():
            return []
        records: list[LabelRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            records.append(
                LabelRecord(
                    case_id=str(raw["case_id"]),
                    cluster_id=str(raw["cluster_id"]),
                    label=ConfirmLabel(str(raw["label"])),
                    score=None if raw.get("score") is None else float(raw["score"]),
                    note=str(raw.get("note", "")),
                    recorded_at=str(raw["recorded_at"]),
                )
            )
        return records

    def resolved(self) -> dict[tuple[str, str], LabelRecord]:
        """The latest label per ``(case_id, cluster_id)``, in first-seen order."""
        latest: dict[tuple[str, str], LabelRecord] = {}
        for record in self.all():
            latest[(record.case_id, record.cluster_id)] = record
        return latest

    def training_pairs(self) -> list[tuple[float, int]]:
        """``(score, label)`` pairs for ``core/calibration.py``.

        Only resolved mine/not_mine labels that carry a recorded score are
        usable; unsure stays a candidate (design section 12) and a scoreless
        label is skipped rather than guessed.
        """
        pairs: list[tuple[float, int]] = []
        for key in sorted(self.resolved()):
            record = self.resolved()[key]
            if record.label is ConfirmLabel.UNSURE or record.score is None:
                continue
            pairs.append((record.score, 1 if record.label is ConfirmLabel.MINE else 0))
        return pairs

    def counts(self) -> dict[str, int]:
        counts = {member.value: 0 for member in ConfirmLabel}
        for record in self.resolved().values():
            counts[record.label.value] += 1
        return counts
