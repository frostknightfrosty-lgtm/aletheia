"""Tests for adapter tier metadata and the construction-time Tier 5 rejection.

The project direction requires every manifest adapter to carry ``legal_tier``,
``enabled_by_default``, ``disabled_reason`` (when disabled), and
``batch_grouping``, with Tier 5 -- the project's hard floor -- refused when the
adapter registry is constructed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from aletheia.core.project_manifest import (
    ProjectManifestError,
    enforce_adapter_tier_policy,
    validate_project_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _entry(**overrides):
    entry = {
        "name": "x",
        "last_audited": "2026-01-01T00:00:00+00:00",
        "verification_status": "verified-fixture",
        "invocation": "Docker / CLI",
        "fixture_provenance": "synthetic",
        "legal_tier": 2,
        "enabled_by_default": True,
        "batch_grouping": None,
    }
    entry.update(overrides)
    return entry


def _validate(entry, tmp_path):
    return validate_project_manifest({"tool_inventory": [entry]}, repo_root=tmp_path)


def test_real_manifest_validates_and_registry_builds_through_enforcement():
    from aletheia.adapters.registry import phase7_adapters

    manifest = json.loads((REPO_ROOT / "PROJECT_MANIFEST.json").read_text(encoding="utf-8"))
    validate_project_manifest(manifest, repo_root=REPO_ROOT)
    adapters = phase7_adapters()
    assert len(adapters) == 56
    entries = {entry["name"].strip().casefold(): entry for entry in manifest["tool_inventory"]}
    for name in adapters:
        assert entries[name.strip().casefold()]["legal_tier"] in {1, 2, 3, 4}


def test_tier_five_is_refused_at_construction():
    with pytest.raises(ProjectManifestError, match="Tier 5"):
        enforce_adapter_tier_policy(["x"], manifest={"tool_inventory": [_entry(legal_tier=5)]})


def test_adapter_without_a_manifest_entry_is_refused():
    with pytest.raises(ProjectManifestError, match="no tool_inventory entry"):
        enforce_adapter_tier_policy(["missing"], manifest={"tool_inventory": [_entry()]})


def test_tier_four_builds_under_the_project_policy():
    enforce_adapter_tier_policy(["x"], manifest={"tool_inventory": [_entry(legal_tier=4)]})


def test_manifest_entry_validation_accepts_the_full_metadata_shape(tmp_path):
    validated = _validate(_entry(), tmp_path)
    assert validated["tool_inventory"][0]["legal_tier"] == 2


@pytest.mark.parametrize("field", ["legal_tier", "enabled_by_default", "batch_grouping"])
def test_missing_adapter_metadata_fails_validation(tmp_path, field):
    entry = _entry()
    del entry[field]
    with pytest.raises(ProjectManifestError, match=field):
        _validate(entry, tmp_path)


@pytest.mark.parametrize("tier", ["2", 6, 0, True])
def test_legal_tier_must_be_an_integer_in_range(tmp_path, tier):
    with pytest.raises(ProjectManifestError, match="legal_tier"):
        _validate(_entry(legal_tier=tier), tmp_path)


def test_enabled_by_default_must_be_boolean(tmp_path):
    with pytest.raises(ProjectManifestError, match="enabled_by_default"):
        _validate(_entry(enabled_by_default="yes"), tmp_path)


def test_disabled_adapter_requires_a_reason(tmp_path):
    with pytest.raises(ProjectManifestError, match="disabled_reason"):
        _validate(_entry(enabled_by_default=False), tmp_path)
    with pytest.raises(ProjectManifestError, match="disabled_reason"):
        _validate(_entry(enabled_by_default=False, disabled_reason="  "), tmp_path)
    validated = _validate(_entry(enabled_by_default=False, disabled_reason="paid subscription"), tmp_path)
    assert validated["tool_inventory"][0]["disabled_reason"] == "paid subscription"


def test_batch_grouping_must_be_string_or_null(tmp_path):
    with pytest.raises(ProjectManifestError, match="batch_grouping"):
        _validate(_entry(batch_grouping=5), tmp_path)
    assert _validate(_entry(batch_grouping="username_enum"), tmp_path)


def test_library_entries_are_not_required_to_carry_adapter_metadata(tmp_path):
    entry = _entry(invocation="Python library")
    del entry["legal_tier"]
    del entry["enabled_by_default"]
    del entry["batch_grouping"]
    del entry["fixture_provenance"]
    validated = _validate(entry, tmp_path)
    assert "legal_tier" not in validated["tool_inventory"][0]
