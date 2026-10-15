from __future__ import annotations

import json
from pathlib import Path

import pytest

from aletheia.core.project_manifest import ProjectManifestError, load_project_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PROJECT_MANIFEST.json"


def test_project_manifest_loads_with_strict_verification_schema():
    manifest = load_project_manifest(MANIFEST)
    assert all("last_audited" in e for e in manifest["tool_inventory"])
    assert all("verification_status" in e for e in manifest["tool_inventory"])
    assert all("verified" not in e for e in manifest["tool_inventory"])


def _write(tmp_path, payload):
    p = tmp_path / "PROJECT_MANIFEST.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _base():
    return {"tool_inventory": [{"name": "x", "last_audited": "2026-10-08T18:38:00+03:00", "verification_status": "unknown", "note": "reason not recorded — flag for review."}]}

def _adapter_base():
    return {"tool_inventory": [{"name": "x", "invocation": "Docker / CLI", "last_audited": "2026-10-08T18:38:00+03:00", "verification_status": "verified-fixture", "fixture_provenance": "synthetic", "note": "synthetic fixture: tests/fixtures/x.txt"}]}


def test_adapter_fixture_provenance_is_required(tmp_path):
    payload = _adapter_base()
    payload["tool_inventory"][0].pop("fixture_provenance")
    with pytest.raises(ProjectManifestError, match="fixture_provenance is required"):
        load_project_manifest(_write(tmp_path, payload))


def test_adapter_fixture_provenance_is_strict(tmp_path):
    payload = _adapter_base()
    payload["tool_inventory"][0]["fixture_provenance"] = "synthetic-ish"
    with pytest.raises(ProjectManifestError, match="fixture_provenance=.*is invalid"):
        load_project_manifest(_write(tmp_path, payload))


def test_old_verified_field_is_rejected(tmp_path):
    payload = _base()
    entry = payload["tool_inventory"][0]
    entry.pop("verification_status")
    entry["verified"] = "2026-10-08"
    with pytest.raises(ProjectManifestError, match="forbidden legacy"):
        load_project_manifest(_write(tmp_path, payload))


def test_invalid_status_is_rejected(tmp_path):
    payload = _base()
    payload["tool_inventory"][0]["verification_status"] = "unverified"
    with pytest.raises(ProjectManifestError, match="is invalid"):
        load_project_manifest(_write(tmp_path, payload))


def test_unknown_requires_nonempty_note(tmp_path):
    payload = _base()
    payload["tool_inventory"][0]["note"] = "  "
    with pytest.raises(ProjectManifestError, match="note is required"):
        load_project_manifest(_write(tmp_path, payload))


def test_asserted_requires_nonempty_note(tmp_path):
    payload = _base()
    payload["tool_inventory"][0]["verification_status"] = "asserted"
    payload["tool_inventory"][0].pop("note")
    with pytest.raises(ProjectManifestError, match="note is required"):
        load_project_manifest(_write(tmp_path, payload))


def test_verified_live_requires_existing_repo_relative_evidence(tmp_path):
    payload = _base()
    payload["tool_inventory"][0]["verification_status"] = "verified-live"
    payload["tool_inventory"][0]["note"] = "authorized run evidence"
    payload["tool_inventory"][0]["evidence"] = "raw/missing.txt"
    with pytest.raises(ProjectManifestError, match="does not exist"):
        load_project_manifest(_write(tmp_path, payload))


def test_verified_live_accepts_existing_evidence(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_text("real container output", encoding="utf-8")
    payload = _base()
    payload["tool_inventory"][0]["verification_status"] = "verified-live"
    payload["tool_inventory"][0]["evidence"] = raw.name
    manifest = load_project_manifest(_write(tmp_path, payload))
    assert manifest["tool_inventory"][0]["evidence"] == raw.name


def test_verified_fixture_adapter_notes_name_existing_fixture_file():
    manifest = load_project_manifest(MANIFEST)
    adapters = [e for e in manifest["tool_inventory"] if "Docker" in str(e.get("invocation", ""))]
    assert len(adapters) == 41
    for entry in adapters:
        assert entry["fixture_provenance"] == "synthetic"
        marker = "fixture file: "
        assert marker in entry["note"], f"Missing {marker!r} marker in {entry['name']} note"
        # Extract the path conservatively between the marker and the next sentence.
        path_text = entry["note"].split(marker, 1)[1].split(". No live", 1)[0]
        assert (ROOT / path_text).is_file(), path_text
