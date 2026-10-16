from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

GENESIS_HASH = "0" * 64
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class AuditChainError(ValueError):
    """Raised when a write would extend an invalid or unanchored audit chain."""


def _root(data_root: str | Path | None) -> Path:
    if data_root is not None:
        return Path(data_root)
    return Path(os.environ.get("ALETHEIA_DATA_DIR", "./data"))


def _run_id(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _audit_path(run_id: str | UUID, data_root: str | Path | None = None) -> Path:
    return _root(data_root) / "runs" / str(_run_id(run_id)) / "AUDIT.jsonl"


def _lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _entry_hash(value: Mapping[str, Any]) -> str:
    unhashed = {key: item for key, item in value.items() if key != "hash"}
    return hashlib.sha256(_canonical_json(unhashed)).hexdigest()


def _event_payload(entry: BaseModel | Mapping[str, Any]) -> tuple[dict[str, Any], UUID]:
    if isinstance(entry, BaseModel):
        payload = entry.model_dump(mode="json")
    elif isinstance(entry, Mapping):
        payload = dict(entry)
    else:
        raise TypeError("audit entry must be a Pydantic model or mapping")

    reserved = {"prev_hash", "hash", "seq"}.intersection(payload)
    if reserved:
        raise ValueError(f"audit entry contains reserved chain fields: {', '.join(sorted(reserved))}")
    if "run_id" not in payload:
        raise ValueError("audit entry must contain run_id")
    try:
        run_id = _run_id(payload["run_id"])
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("audit entry run_id must be a UUID") from exc
    payload["run_id"] = str(run_id)
    return payload, run_id


def _read_log(path: Path, run_id: UUID) -> dict[str, Any]:
    if not path.exists():
        return {"valid": True, "entries": [], "hashes": {GENESIS_HASH: 0}, "tip_hash": GENESIS_HASH, "first_broken_seq": None}
    raw = path.read_bytes()
    if not raw:
        return {"valid": True, "entries": [], "hashes": {GENESIS_HASH: 0}, "tip_hash": GENESIS_HASH, "first_broken_seq": None}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"valid": False, "entries": [], "hashes": {GENESIS_HASH: 0}, "tip_hash": GENESIS_HASH, "first_broken_seq": 1}

    lines = text.splitlines()
    entries: list[dict[str, Any]] = []
    hashes = {GENESIS_HASH: 0}
    previous_hash = GENESIS_HASH
    for expected_seq, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return {"valid": False, "entries": entries, "hashes": hashes, "tip_hash": previous_hash, "first_broken_seq": expected_seq}
        if not isinstance(record, dict):
            return {"valid": False, "entries": entries, "hashes": hashes, "tip_hash": previous_hash, "first_broken_seq": expected_seq}
        if record.get("seq") != expected_seq or record.get("run_id") != str(run_id):
            return {"valid": False, "entries": entries, "hashes": hashes, "tip_hash": previous_hash, "first_broken_seq": expected_seq}
        if record.get("prev_hash") != previous_hash:
            return {"valid": False, "entries": entries, "hashes": hashes, "tip_hash": previous_hash, "first_broken_seq": expected_seq}
        recorded_hash = record.get("hash")
        if not isinstance(recorded_hash, str) or recorded_hash != _entry_hash(record):
            return {"valid": False, "entries": entries, "hashes": hashes, "tip_hash": previous_hash, "first_broken_seq": expected_seq}
        entries.append(record)
        hashes[recorded_hash] = expected_seq
        previous_hash = recorded_hash

    if not text.endswith("\n"):
        broken_seq = len(lines) or 1
        valid_entries = entries[:-1]
        valid_tip = valid_entries[-1]["hash"] if valid_entries else GENESIS_HASH
        return {
            "valid": False,
            "entries": valid_entries,
            "hashes": {key: seq for key, seq in hashes.items() if seq < broken_seq},
            "tip_hash": valid_tip,
            "first_broken_seq": broken_seq,
        }
    return {"valid": True, "entries": entries, "hashes": hashes, "tip_hash": previous_hash, "first_broken_seq": None}


def _read_manifest(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    manifest_path = path.parent / "MANIFEST.json"
    if not manifest_path.exists():
        return None, None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unable to read run manifest: {exc}"
    if not isinstance(manifest, dict):
        return None, "run manifest root is not an object"
    return manifest, None


def _checkpoint_hash_valid(manifest: Mapping[str, Any]) -> bool:
    checkpoint_hash = manifest.get("checkpoint_hash")
    if checkpoint_hash is None:
        return True
    from aletheia.core.checkpoint import CheckpointStore

    return checkpoint_hash == CheckpointStore._hash_manifest(dict(manifest))


def _publish_tip(path: Path, run_id: UUID, tip_hash: str) -> None:
    manifest, error = _read_manifest(path)
    if error:
        raise AuditChainError(error)
    if manifest is None:
        return
    from aletheia.core.checkpoint import CheckpointStore

    CheckpointStore(path.parent.parent).save(run_id, {**manifest, "chain_tip": tip_hash})


def append(
    entry: BaseModel | Mapping[str, Any],
    *,
    audit_path: str | Path | None = None,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """Append one canonical audit entry and publish its tip in the run manifest."""
    payload, run_id = _event_payload(entry)
    path = Path(audit_path) if audit_path is not None else _audit_path(run_id, data_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    with _lock(path):
        state = _read_log(path, run_id)
        if not state["valid"]:
            raise AuditChainError(f"existing audit chain breaks at sequence {state['first_broken_seq']}")
        manifest, error = _read_manifest(path)
        if error:
            raise AuditChainError(error)
        if manifest is not None:
            if not _checkpoint_hash_valid(manifest):
                raise AuditChainError("run manifest checkpoint_hash is invalid")
            anchor = manifest.get("chain_tip")
            if anchor is None and state["entries"]:
                raise AuditChainError("run manifest has no chain_tip for existing audit entries")
            if anchor is not None and anchor != state["tip_hash"]:
                raise AuditChainError("run manifest chain_tip does not match the audit chain")

        record: dict[str, Any] = {
            **payload,
            "seq": len(state["entries"]) + 1,
            "prev_hash": state["tip_hash"],
        }
        record["hash"] = _entry_hash(record)
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        _publish_tip(path, run_id, record["hash"])
        return record


def verify(run_id: str | UUID, *, data_root: str | Path | None = None) -> dict[str, Any]:
    """Verify entry links and the run manifest's chain-tip/checkpoint anchors."""
    normalized_id = _run_id(run_id)
    path = _audit_path(normalized_id, data_root)
    state = _read_log(path, normalized_id)
    result: dict[str, Any] = {
        "valid": state["valid"],
        "first_broken_seq": state["first_broken_seq"],
        "tip_hash": state["tip_hash"],
        "anchored": False,
    }
    if not state["valid"]:
        return result
    manifest, error = _read_manifest(path)
    if error:
        result.update({"valid": False, "first_broken_seq": len(state["entries"]) + 1, "error": error})
        return result
    if manifest is None:
        return result
    if not _checkpoint_hash_valid(manifest):
        result.update({
            "valid": False,
            "first_broken_seq": len(state["entries"]) + 1,
            "error": "run manifest checkpoint_hash is invalid",
        })
        return result
    anchor = manifest.get("chain_tip")
    if anchor is None:
        if state["entries"]:
            result.update({"valid": False, "first_broken_seq": 1, "error": "run manifest has no chain_tip"})
        return result
    result["anchored"] = True
    if anchor != state["tip_hash"]:
        anchor_seq = state["hashes"].get(anchor)
        first_broken = anchor_seq + 1 if anchor_seq is not None else len(state["entries"]) + 1
        result.update({
            "valid": False,
            "first_broken_seq": first_broken,
            "error": "run manifest chain_tip does not match the audit chain",
        })
    return result


def tip(run_id: str | UUID, *, data_root: str | Path | None = None) -> str:
    """Return the current tip only when it still matches the run-manifest anchor."""
    normalized_id = _run_id(run_id)
    path = _audit_path(normalized_id, data_root)
    state = _read_log(path, normalized_id)
    if not state["valid"]:
        raise AuditChainError(f"audit chain breaks at sequence {state['first_broken_seq']}")
    manifest, error = _read_manifest(path)
    if error:
        raise AuditChainError(error)
    if manifest is not None:
        if not _checkpoint_hash_valid(manifest):
            raise AuditChainError("run manifest checkpoint_hash is invalid")
        anchor = manifest.get("chain_tip")
        if anchor is None and state["entries"]:
            raise AuditChainError("run manifest has no chain_tip for existing audit entries")
        if anchor is not None and anchor != state["tip_hash"]:
            raise AuditChainError("run manifest chain_tip does not match the audit chain")
    return state["tip_hash"]
