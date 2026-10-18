"""Subject-centric case file with snapshots and a timeline (P17.7).

Design of record: ``docs/PIVOT_CASCADE.md`` section 9 — "runs merge into one
subject-centric identity graph with snapshots and a timeline (events: first
seen, updated, retracted); reports are per run + cumulative dossier" — plus
the re-audit/watch diff ("new appearances, changed bios, new exposures,
resolved blind spots").

Storage: one JSON document per case under ``<root>/<case_id>.json``, written
atomically (temp file + replace) like the run manifests. The case file is
local state under the data root and is never committed; nothing here touches
the network.

Snapshots are mappings of ``section -> {stable key: JSON value}`` (for
example ``appearances``, ``exposures``, ``blind_spots``); :func:`diff_snapshots`
reports added, removed, and changed entries per section. Timeline events are
append-only records (``run_recorded``, ``snapshot``, and free-form events such
as ``retracted``).

Honest limits: v1 keeps full snapshot history in one JSON file (fine at
cascade scales; revisit if cases grow dense), and diffs are structural, not
semantic — a changed bio string is reported as changed, and judging whether
the change matters stays with the report layer.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from aletheia.core.models import Seed, utc_now

__all__ = ["CaseDiff", "CaseStore", "diff_snapshots"]


@dataclass(frozen=True)
class CaseDiff:
    """Structural diff between two snapshots, section by section."""

    added: dict[str, dict[str, Any]]
    removed: dict[str, dict[str, Any]]
    changed: dict[str, dict[str, tuple[Any, Any]]]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def summary(self) -> str:
        if self.is_empty:
            return "no changes"
        parts: list[str] = []
        entries = sum(len(section) for section in self.added.values())
        if entries:
            parts.append(f"{entries} added")
        entries = sum(len(section) for section in self.removed.values())
        if entries:
            parts.append(f"{entries} removed")
        entries = sum(len(section) for section in self.changed.values())
        if entries:
            parts.append(f"{entries} changed")
        return "; ".join(parts)


def diff_snapshots(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
) -> CaseDiff:
    """Compare two snapshots section by section, deterministically."""
    added: dict[str, dict[str, Any]] = {}
    removed: dict[str, dict[str, Any]] = {}
    changed: dict[str, dict[str, tuple[Any, Any]]] = {}
    for section in sorted(set(before) | set(after)):
        before_section = dict(before.get(section, {}))
        after_section = dict(after.get(section, {}))
        for key in sorted(set(after_section) - set(before_section)):
            added.setdefault(section, {})[key] = after_section[key]
        for key in sorted(set(before_section) - set(after_section)):
            removed.setdefault(section, {})[key] = before_section[key]
        for key in sorted(set(before_section) & set(after_section)):
            if before_section[key] != after_section[key]:
                changed.setdefault(section, {})[key] = (
                    before_section[key],
                    after_section[key],
                )
    return CaseDiff(added=added, removed=removed, changed=changed)


class CaseStore:
    """JSON-file case memory under the data root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    # -- files ----------------------------------------------------------------

    def _path(self, case_id: UUID) -> Path:
        return self.root / f"{case_id}.json"

    def exists(self, case_id: UUID) -> bool:
        return self._path(case_id).exists()

    def _load_raw(self, case_id: UUID) -> dict[str, Any]:
        path = self._path(case_id)
        if not path.exists():
            raise FileNotFoundError(f"unknown case {case_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_raw(self, case_id: UUID, payload: dict[str, Any]) -> None:
        path = self._path(case_id)
        payload = {**payload, "updated_at": utc_now().isoformat()}
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        fd, tmp = tempfile.mkstemp(prefix="case.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # -- cases ----------------------------------------------------------------

    def create(self, subject_seeds: Sequence[Seed], *, label: str = "") -> UUID:
        if not subject_seeds:
            raise ValueError("a case needs at least one subject seed")
        case_id = uuid4()
        payload = {
            "case_id": str(case_id),
            "label": label,
            "subject_seeds": [seed.model_dump(mode="json") for seed in subject_seeds],
            "created_at": utc_now().isoformat(),
            "runs": [],
            "timeline": [],
            "snapshots": [],
        }
        self._save_raw(case_id, payload)
        return case_id

    def load(self, case_id: UUID) -> dict[str, Any]:
        return self._load_raw(case_id)

    def list_cases(self) -> list[dict[str, Any]]:
        cases = [self._load_raw(UUID(path.stem)) for path in sorted(self.root.glob("*.json"))]
        return sorted(cases, key=lambda case: (case.get("created_at", ""), case["case_id"]))

    def purge(self, case_id: UUID) -> dict[str, Any]:
        """Delete the case file; returns an inventory of what was removed.

        Purge is the only deletion path in the case model (design section 11:
        "a ``purge`` command deletes case artifacts on request"); everything
        else is append-only. Unknown cases raise ``FileNotFoundError``.
        """
        payload = self._load_raw(case_id)
        self._path(case_id).unlink()
        return {
            "case_id": str(case_id),
            "runs_removed": len(payload.get("runs", [])),
            "snapshots_removed": len(payload.get("snapshots", [])),
            "timeline_events": len(payload.get("timeline", [])),
        }

    # -- runs and timeline ----------------------------------------------------

    def record_run(
        self,
        case_id: UUID,
        *,
        run_id: UUID,
        summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._load_raw(case_id)
        entry = {
            "run_id": str(run_id),
            "recorded_at": utc_now().isoformat(),
            "summary": dict(summary or {}),
        }
        payload["runs"].append(entry)
        payload["timeline"].append(
            {"at": entry["recorded_at"], "event": "run_recorded", "run_id": str(run_id)}
        )
        self._save_raw(case_id, payload)
        return entry

    def record_event(self, case_id: UUID, event: str, **details: Any) -> dict[str, Any]:
        if not event.strip():
            raise ValueError("event name must be non-empty")
        payload = self._load_raw(case_id)
        entry = {"at": utc_now().isoformat(), "event": event, **details}
        payload["timeline"].append(entry)
        self._save_raw(case_id, payload)
        return entry

    def timeline(self, case_id: UUID) -> list[dict[str, Any]]:
        return list(self._load_raw(case_id)["timeline"])

    # -- snapshots and diffs --------------------------------------------------

    def snapshot(self, case_id: UUID, sections: Mapping[str, Mapping[str, Any]]) -> str:
        payload = self._load_raw(case_id)
        snapshot_id = str(uuid4())
        taken_at = utc_now().isoformat()
        payload["snapshots"].append(
            {
                "snapshot_id": snapshot_id,
                "taken_at": taken_at,
                "sections": {name: dict(entries) for name, entries in sections.items()},
            }
        )
        payload["timeline"].append(
            {"at": taken_at, "event": "snapshot", "snapshot_id": snapshot_id}
        )
        self._save_raw(case_id, payload)
        return snapshot_id

    def snapshots(self, case_id: UUID) -> list[dict[str, Any]]:
        return list(self._load_raw(case_id)["snapshots"])

    def last_snapshot(self, case_id: UUID) -> dict[str, Any] | None:
        snapshots = self._load_raw(case_id)["snapshots"]
        return snapshots[-1] if snapshots else None

    def diff_against_last(
        self,
        case_id: UUID,
        sections: Mapping[str, Mapping[str, Any]],
    ) -> CaseDiff | None:
        """Diff a fresh snapshot against the case's last one (None if no history).

        This is the re-audit/watch diff input: "new appearances, changed bios,
        new exposures, resolved blind spots". Whether an unchanged item is
        re-asked stays with the cache layer (section 9).
        """
        last = self.last_snapshot(case_id)
        if last is None:
            return None
        return diff_snapshots(last["sections"], sections)
