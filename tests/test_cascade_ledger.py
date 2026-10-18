"""Tests for the append-only decision ledger (P17.6)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aletheia.cascade.ledger import DecisionLedger
from aletheia.core.chain import GENESIS_HASH

_FIXED = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)


def _clock() -> datetime:
    return _FIXED


def test_append_sequences_and_links_hashes():
    ledger = DecisionLedger(clock=_clock)
    first = ledger.append("pivot_proposed", {"priority": 0.25})
    second = ledger.append("pivot_granted", {"expansion_number": 1})
    assert first.sequence == 1
    assert second.sequence == 2
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash
    assert first.hash != second.hash
    ok, detail = ledger.verify()
    assert ok is True
    assert detail == "2 entries verified"


def test_payload_and_kind_validation():
    ledger = DecisionLedger(clock=_clock)
    with pytest.raises(ValueError):
        ledger.append("", {})
    with pytest.raises(ValueError):
        ledger.append("   ", {})
    with pytest.raises(ValueError):
        ledger.append("stop", {"hash": "x"})
    with pytest.raises(ValueError):
        ledger.append("stop", {"sequence": 1})
    with pytest.raises(ValueError):
        ledger.append("note", {"bad": {1, 2}})


def test_tamper_detection_and_round_trip():
    ledger = DecisionLedger(clock=_clock)
    ledger.append("a", {"n": 1})
    ledger.append("b", {"n": 2})
    ledger.append("c", {"n": 3})
    records = ledger.to_dicts()
    reloaded = DecisionLedger.from_dicts(records)
    assert reloaded.entries() == ledger.entries()
    records[1] = {**records[1], "payload": {"n": 999}}
    with pytest.raises(ValueError):
        DecisionLedger.from_dicts(records)
    broken = DecisionLedger.from_dicts(records, verify=False)
    ok, detail = broken.verify()
    assert ok is False
    assert "hash mismatch at sequence 2" in detail


def test_sequence_break_detection():
    ledger = DecisionLedger(clock=_clock)
    ledger.append("a", {})
    records = ledger.to_dicts()
    records[0] = {**records[0], "sequence": 5}
    broken = DecisionLedger.from_dicts(records, verify=False)
    ok, detail = broken.verify()
    assert ok is False
    assert "sequence break" in detail


def test_replay_filter_and_order():
    ledger = DecisionLedger(clock=_clock)
    ledger.append("pivot_proposed", {"i": 1})
    ledger.append("stop", {"i": 2})
    ledger.append("pivot_proposed", {"i": 3})
    assert [entry.kind for entry in ledger.replay()] == ["pivot_proposed", "stop", "pivot_proposed"]
    filtered = [entry.payload["i"] for entry in ledger.replay(kinds=["pivot_proposed"])]
    assert filtered == [1, 3]
    assert len(ledger) == 3


def test_fixed_clock_hashes_are_deterministic():
    first = DecisionLedger(clock=_clock)
    first.append("a", {"n": 1})
    first.append("b", {"n": 2})
    second = DecisionLedger(clock=_clock)
    second.append("a", {"n": 1})
    second.append("b", {"n": 2})
    assert first.to_dicts() == second.to_dicts()
