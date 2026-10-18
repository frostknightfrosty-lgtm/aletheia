"""Tests for the cascade CLI group (P17.8)."""

from __future__ import annotations

import json
import sys

import pytest

from aletheia.cascade.ledger import DecisionLedger
from aletheia.cli.main import main
from aletheia.core.case_store import CaseStore
from aletheia.core.labels import LabelStore
from aletheia.core.models import Seed, SeedType


def _run(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["aletheia", *argv])
    main()


def test_cli_review_replays_and_verifies(tmp_path, monkeypatch, capsys):
    ledger = DecisionLedger()
    ledger.append("pivot_proposed", {"seed_value": "alice"})
    ledger.append("stop", {"reason": "user_stop"})
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        "\n".join(json.dumps(record) for record in ledger.to_dicts()) + "\n",
        encoding="utf-8",
    )
    _run(monkeypatch, ["cascade", "review", "--ledger", str(path)])
    out = capsys.readouterr().out
    assert "ledger: 2 entries verified" in out
    assert "pivot_proposed" in out
    assert "stop" in out

    _run(monkeypatch, ["cascade", "review", "--ledger", str(path), "--kinds", "stop"])
    filtered = capsys.readouterr().out
    assert "stop" in filtered
    assert "pivot_proposed" not in filtered


def test_cli_review_rejects_a_broken_ledger(tmp_path, monkeypatch, capsys):
    ledger = DecisionLedger()
    ledger.append("a", {"n": 1})
    records = ledger.to_dicts()
    records[0]["payload"] = {"n": 999}
    path = tmp_path / "broken.jsonl"
    path.write_text(json.dumps(records), encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, ["cascade", "review", "--ledger", str(path)])
    assert excinfo.value.code == 1
    assert "invalid ledger" in capsys.readouterr().out


def test_cli_confirm_and_purge(tmp_path, monkeypatch, capsys):
    data_dir = tmp_path / "data"
    _run(
        monkeypatch,
        [
            "cascade",
            "confirm",
            "--case-id",
            "c1",
            "--cluster-id",
            "k1",
            "--label",
            "mine",
            "--score",
            "3.5",
            "--data-dir",
            str(data_dir),
        ],
    )
    out = capsys.readouterr().out
    assert "recorded: c1/k1 = mine" in out
    store = LabelStore(data_dir / "labels.jsonl")
    assert store.all()[0].score == 3.5

    case_store = CaseStore(data_dir / "cases")
    case_id = case_store.create([Seed(type=SeedType.USERNAME, value="alice")])
    store.add(case_id=str(case_id), cluster_id="k1", label="not_mine")
    _run(monkeypatch, ["cascade", "purge", "--case-id", str(case_id), "--data-dir", str(data_dir)])
    out = capsys.readouterr().out
    assert "case file: deleted" in out
    assert "labels removed: 1" in out
    assert case_store.exists(case_id) is False
    assert [record.case_id for record in store.all()] == ["c1"]
