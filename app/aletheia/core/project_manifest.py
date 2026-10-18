"""Strict loader for the repository-level PROJECT_MANIFEST.json.

The repository manifest is evidence metadata, not a runtime investigation
checkpoint. Loading is intentionally fail-closed: stale verification fields,
unknown statuses, missing audit timestamps, unsupported status notes, and
missing live evidence artifacts make the manifest invalid.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

FIXTURE_PROVENANCE_VALUES = frozenset({"synthetic", "captured"})

VERIFICATION_STATUSES = frozenset(
    {
        "verified-live",
        "verified-fixture",
        "verified-source-read",
        "unverified-fixture",
        "asserted",
        "unknown",
        "blocked",
    }
)

_REQUIRED_ENTRY_FIELDS = {"name", "last_audited", "verification_status"}
_FORBIDDEN_ENTRY_FIELDS = {"verified", "verified_date", "last_verified"}
# The project direction requires every manifest adapter to carry these fields so
# the legal tier, default-enablement decision, and batch grouping are auditable
# metadata rather than folklore.
_ADAPTER_METADATA_FIELDS = {"legal_tier", "enabled_by_default", "batch_grouping"}


class ProjectManifestError(ValueError):
    """Raised when PROJECT_MANIFEST.json violates the evidence schema."""


def _fail(message: str) -> None:
    raise ProjectManifestError(message)


def _validate_entry(entry: Mapping[str, Any], *, index: int, repo_root: Path) -> None:
    label = f"tool_inventory[{index}]"
    old = sorted(_FORBIDDEN_ENTRY_FIELDS & entry.keys())
    if old:
        _fail(f"{label} contains forbidden legacy verification field(s): {', '.join(old)}")

    missing = sorted(_REQUIRED_ENTRY_FIELDS - entry.keys())
    if missing:
        _fail(f"{label} missing required field(s): {', '.join(missing)}")

    status = entry["verification_status"]
    if status not in VERIFICATION_STATUSES:
        allowed = ", ".join(sorted(VERIFICATION_STATUSES))
        _fail(f"{label}.verification_status={status!r} is invalid; allowed: {allowed}")

    last_audited = entry["last_audited"]
    if not isinstance(last_audited, str) or not last_audited.strip():
        _fail(f"{label}.last_audited must be a non-empty timestamp string")
    try:
        datetime.fromisoformat(last_audited)
    except ValueError as exc:
        _fail(f"{label}.last_audited must be an ISO-8601 timestamp: {last_audited!r}")

    note = entry.get("note")
    if status in {"asserted", "unknown"}:
        if not isinstance(note, str) or not note.strip():
            _fail(f"{label}.note is required and non-empty for status {status!r}")

    is_adapter = "Docker" in str(entry.get("invocation", ""))
    if is_adapter:
        if "fixture_provenance" not in entry:
            _fail(f"{label}.fixture_provenance is required for adapter entries")
        provenance = entry["fixture_provenance"]
        if provenance not in FIXTURE_PROVENANCE_VALUES:
            allowed_provenance = ", ".join(sorted(FIXTURE_PROVENANCE_VALUES))
            _fail(f"{label}.fixture_provenance={provenance!r} is invalid; allowed: {allowed_provenance}")

        missing_metadata = sorted(_ADAPTER_METADATA_FIELDS - entry.keys())
        if missing_metadata:
            _fail(f"{label} missing adapter metadata field(s): {', '.join(missing_metadata)}")

        tier = entry["legal_tier"]
        if isinstance(tier, bool) or not isinstance(tier, int) or not 1 <= tier <= 5:
            _fail(f"{label}.legal_tier must be an integer 1..5, got {tier!r}")

        if not isinstance(entry["enabled_by_default"], bool):
            _fail(f"{label}.enabled_by_default must be a boolean")

        grouping = entry["batch_grouping"]
        if grouping is not None and not isinstance(grouping, str):
            _fail(f"{label}.batch_grouping must be a string or null")

        if entry["enabled_by_default"] is False:
            reason = entry.get("disabled_reason")
            if not isinstance(reason, str) or not reason.strip():
                _fail(f"{label}.disabled_reason is required and non-empty when enabled_by_default is false")

    if status == "verified-live":
        evidence = entry.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            _fail(f"{label}.evidence must point to a raw artifact path for verified-live")
        evidence_path = Path(evidence)
        if evidence_path.is_absolute() or ".." in evidence_path.parts:
            _fail(f"{label}.evidence must be a repository-relative path: {evidence!r}")
        resolved = (repo_root / evidence_path).resolve()
        if repo_root.resolve() not in resolved.parents and resolved != repo_root.resolve():
            _fail(f"{label}.evidence escapes repository root: {evidence!r}")
        if not resolved.exists() or not resolved.is_file():
            _fail(f"{label}.evidence does not exist as a file in the repository: {evidence!r}")


def validate_project_manifest(manifest: Mapping[str, Any], *, repo_root: Path) -> dict[str, Any]:
    """Validate and return a detached copy of a project manifest."""
    if not isinstance(manifest, Mapping):
        _fail("PROJECT_MANIFEST.json root must be an object")
    inventory = manifest.get("tool_inventory")
    if not isinstance(inventory, list):
        _fail("PROJECT_MANIFEST.json must contain a tool_inventory list")

    names: set[str] = set()
    for index, entry in enumerate(inventory):
        if not isinstance(entry, Mapping):
            _fail(f"tool_inventory[{index}] must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            _fail(f"tool_inventory[{index}].name must be a non-empty string")
        if name in names:
            _fail(f"duplicate tool_inventory entry: {name!r}")
        names.add(name)
        _validate_entry(entry, index=index, repo_root=repo_root)

    return json.loads(json.dumps(manifest))


def load_project_manifest(path: str | Path) -> dict[str, Any]:
    """Load PROJECT_MANIFEST.json and fail loudly on evidence-schema errors."""
    manifest_path = Path(path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectManifestError(f"invalid JSON in {manifest_path}: {exc}") from exc
    except OSError as exc:
        raise ProjectManifestError(f"unable to read manifest {manifest_path}: {exc}") from exc
    return validate_project_manifest(manifest, repo_root=manifest_path.parent)


def enforce_adapter_tier_policy(adapter_names: Iterable[str], *, manifest: Mapping[str, Any]) -> None:
    """Construction-time rejection of Tier 5 adapters.

    Called while the adapter registry is built: every constructed adapter must
    have a tool_inventory entry, and an entry that declares ``legal_tier: 5``
    refuses construction outright - Tier 5 is the project's hard floor, not a
    review state. Tiers 1-4 (including Tier 4, enabled under the project policy)
    build normally.
    """
    entries = {
        str(entry.get("name", "")).strip().casefold(): entry
        for entry in manifest.get("tool_inventory", [])
        if isinstance(entry, Mapping)
    }
    for name in adapter_names:
        entry = entries.get(name.strip().casefold())
        if entry is None:
            _fail(f"adapter {name!r} has no tool_inventory entry, so its legal tier cannot be established")
        if entry.get("legal_tier") == 5:
            _fail(
                f"adapter {name!r} declares legal_tier=5; "
                "Tier 5 is outside the project floor and construction is refused"
            )
