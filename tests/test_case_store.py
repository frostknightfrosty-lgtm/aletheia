"""Tests for the subject-centric case store (P17.7)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from aletheia.core.case_store import CaseStore, diff_snapshots
from aletheia.core.models import Seed, SeedType


def _seeds():
    return [Seed(type=SeedType.USERNAME, value="frost2233")]


def test_create_load_and_list(tmp_path):
    store = CaseStore(tmp_path / "cases")
    case_id = store.create([Seed(type=SeedType.USERNAME, value="alice")], label="self-audit")
    assert store.exists(case_id)
    payload = store.load(case_id)
    assert payload["label"] == "self-audit"
    assert payload["subject_seeds"][0]["value"] == "alice"
    assert payload["runs"] == []
    assert payload["timeline"] == []
    assert payload["snapshots"] == []
    assert [case["case_id"] for case in store.list_cases()] == [str(case_id)]


def test_unknown_case_raises(tmp_path):
    store = CaseStore(tmp_path / "cases")
    with pytest.raises(FileNotFoundError):
        store.load(uuid4())


def test_create_requires_seeds(tmp_path):
    store = CaseStore(tmp_path / "cases")
    with pytest.raises(ValueError):
        store.create([])


def test_record_run_appends_run_and_timeline(tmp_path):
    store = CaseStore(tmp_path / "cases")
    case_id = store.create(_seeds())
    run_id = uuid4()
    entry = store.record_run(case_id, run_id=run_id, summary={"tier": "confirmed"})
    assert entry["run_id"] == str(run_id)
    assert store.load(case_id)["runs"][0]["summary"] == {"tier": "confirmed"}
    timeline = store.timeline(case_id)
    assert [event["event"] for event in timeline] == ["run_recorded"]
    assert timeline[0]["run_id"] == str(run_id)


def test_snapshot_and_diff_against_last(tmp_path):
    store = CaseStore(tmp_path / "cases")
    case_id = store.create(_seeds())
    assert store.last_snapshot(case_id) is None
    assert store.diff_against_last(case_id, {}) is None
    first = {
        "appearances": {"github:alice": {"bio": "old"}, "x:alice": {"bio": "x"}},
        "exposures": {"breach:a": {"date": "2019"}},
    }
    snapshot_id = store.snapshot(case_id, first)
    assert store.last_snapshot(case_id)["snapshot_id"] == snapshot_id
    second = {
        "appearances": {"github:alice": {"bio": "new"}},
        "exposures": {},
        "blind_spots": {"hibp": "paid wall"},
    }
    diff = store.diff_against_last(case_id, second)
    assert diff is not None
    assert diff.added == {"blind_spots": {"hibp": "paid wall"}}
    assert diff.removed == {
        "appearances": {"x:alice": {"bio": "x"}},
        "exposures": {"breach:a": {"date": "2019"}},
    }
    assert diff.changed == {
        "appearances": {"github:alice": ({"bio": "old"}, {"bio": "new"})}
    }
    assert diff.is_empty is False
    assert "1 added" in diff.summary()
    assert "1 changed" in diff.summary()
    assert "2 removed" in diff.summary()


def test_empty_diff_and_no_temp_files_left(tmp_path):
    root = tmp_path / "cases"
    store = CaseStore(root)
    case_id = store.create(_seeds())
    sections = {"appearances": {"a": 1}}
    store.snapshot(case_id, sections)
    diff = store.diff_against_last(case_id, sections)
    assert diff is not None and diff.is_empty
    assert diff.summary() == "no changes"
    assert list(root.glob("*.tmp")) == []


def test_diff_snapshots_is_deterministic_and_pure():
    before = {"b": {"2": "x", "1": "y"}, "a": {}}
    after = {"a": {"n": 1}, "b": {"1": "z"}}
    diff = diff_snapshots(before, after)
    assert list(diff.added) == ["a"]
    assert diff.added["a"] == {"n": 1}
    assert diff.changed["b"]["1"] == ("y", "z")
    assert diff.removed == {"b": {"2": "x"}}
    assert before == {"b": {"2": "x", "1": "y"}, "a": {}}
    assert after == {"a": {"n": 1}, "b": {"1": "z"}}


def test_record_event_validates_and_appends(tmp_path):
    store = CaseStore(tmp_path / "cases")
    case_id = store.create(_seeds())
    store.record_event(case_id, "retracted", claim_id="c1", reason="not mine")
    events = store.timeline(case_id)
    assert events[-1]["event"] == "retracted"
    assert events[-1]["claim_id"] == "c1"
    with pytest.raises(ValueError):
        store.record_event(case_id, "   ")
