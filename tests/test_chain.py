import json
import sys
from datetime import timedelta
from uuid import uuid4

import pytest

from aletheia.adapters.phase5c import RdapAdapter
from aletheia.cli.main import main
from aletheia.core.audit import AuditLogger
from aletheia.core.checkpoint import CheckpointStore
from aletheia.core.chain import AuditChainError
from aletheia.core.models import AdapterRunResult, AuditEvent, Seed, SeedType, utc_now
from aletheia.core.orchestrator import Orchestrator
from aletheia.core import chain


def _new_run(data_root, run_id=None):
    run_id = run_id or uuid4()
    CheckpointStore(data_root / "runs").save(
        run_id,
        {"goal": "audit chain test", "chain_tip": chain.GENESIS_HASH},
    )
    return run_id


def _append_entries(data_root, run_id, count=5, changed_at=None):
    for ordinal in range(count):
        value = "changed" if ordinal == changed_at else f"event-{ordinal}"
        chain.append(
            {"run_id": str(run_id), "event_type": value, "ordinal": ordinal},
            data_root=data_root,
        )


def test_five_entries_form_a_stable_chain_tip(tmp_path):
    run_id = _new_run(tmp_path)
    _append_entries(tmp_path, run_id)

    audit_path = tmp_path / "runs" / str(run_id) / "AUDIT.jsonl"
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    result = chain.verify(run_id, data_root=tmp_path)
    tip_hash = chain.tip(run_id, data_root=tmp_path)

    assert len(entries) == 5
    assert entries[0]["seq"] == 1
    assert entries[0]["prev_hash"] == chain.GENESIS_HASH
    assert all(entry["seq"] == index for index, entry in enumerate(entries, 1))
    assert all(entries[index]["prev_hash"] == entries[index - 1]["hash"] for index in range(1, 5))
    assert result["valid"] is True
    assert result["first_broken_seq"] is None
    assert result["tip_hash"] == tip_hash
    assert chain.tip(run_id, data_root=tmp_path) == tip_hash
    assert CheckpointStore(tmp_path / "runs").load(run_id)["chain_tip"] == tip_hash


def test_editing_middle_entry_is_detected_at_its_sequence(tmp_path):
    run_id = _new_run(tmp_path)
    _append_entries(tmp_path, run_id)
    audit_path = tmp_path / "runs" / str(run_id) / "AUDIT.jsonl"
    original_tip = chain.tip(run_id, data_root=tmp_path)
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    entries[2]["event_type"] = "tampered-event"
    audit_path.write_text("".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries), encoding="utf-8")

    result = chain.verify(run_id, data_root=tmp_path)

    assert result["valid"] is False
    assert result["first_broken_seq"] == 3
    assert result["tip_hash"] != original_tip


def test_tip_changes_when_an_entry_changes(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    run_id = uuid4()
    first_run = _new_run(first_root, run_id)
    second_run = _new_run(second_root, run_id)
    _append_entries(first_root, first_run)
    _append_entries(second_root, second_run, changed_at=2)

    assert chain.tip(first_run, data_root=first_root) != chain.tip(second_run, data_root=second_root)


def test_removing_the_final_entry_breaks_the_manifest_anchor(tmp_path):
    run_id = _new_run(tmp_path)
    _append_entries(tmp_path, run_id)
    audit_path = tmp_path / "runs" / str(run_id) / "AUDIT.jsonl"
    entries = audit_path.read_text(encoding="utf-8").splitlines()
    audit_path.write_text("\n".join(entries[:-1]) + "\n", encoding="utf-8")

    result = chain.verify(run_id, data_root=tmp_path)

    assert result["valid"] is False
    assert result["first_broken_seq"] == 5
    with pytest.raises(AuditChainError, match="chain_tip"):
        chain.tip(run_id, data_root=tmp_path)


def test_audit_logger_appends_chained_events_and_updates_manifest(tmp_path):
    run_id = _new_run(tmp_path)
    audit_path = tmp_path / "runs" / str(run_id) / "AUDIT.jsonl"
    logger = AuditLogger(audit_path)
    logger.log(AuditEvent(run_id=run_id, event_type="phase2_finalize", outcome="succeeded"))

    result = chain.verify(run_id, data_root=tmp_path)

    assert result["valid"] is True
    assert result["first_broken_seq"] is None
    assert result["tip_hash"] == CheckpointStore(tmp_path / "runs").load(run_id)["chain_tip"]


def test_completed_orchestrator_run_publishes_verified_chain_tip(tmp_path, monkeypatch):
    orchestrator = Orchestrator(tmp_path)
    adapter = RdapAdapter()

    def fake_run(request, workspace, audit_logger):
        workspace.mkdir(parents=True, exist_ok=True)
        audit_logger.log(AuditEvent(run_id=request.run_id, event_type="adapter_complete", adapter="rdap"))
        started = utc_now()
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=adapter.descriptor,
            status="succeeded",
            started_at=started,
            finished_at=started + timedelta(milliseconds=1),
        )

    monkeypatch.setattr(adapter, "run", fake_run)
    orchestrator.adapters = {"rdap": adapter}
    run_id = orchestrator.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))

    # Offline replay: no egress wiring, so this test needs no Docker daemon.
    manifest = orchestrator.resume(run_id, wire_egress=False)

    assert manifest["chain_tip"] == chain.tip(run_id, data_root=tmp_path)
    assert chain.verify(run_id, data_root=tmp_path)["valid"] is True


def test_append_does_not_repair_a_tampered_checkpoint_hash(tmp_path):
    run_id = _new_run(tmp_path)
    manifest_path = tmp_path / "runs" / str(run_id) / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["checkpoint_hash"] = "tampered"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AuditChainError, match="checkpoint_hash"):
        chain.append({"run_id": str(run_id), "event_type": "must-not-append"}, data_root=tmp_path)

    saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved_manifest["checkpoint_hash"] == "tampered"


def test_append_refuses_to_advance_a_stale_manifest_anchor(tmp_path):
    run_id = _new_run(tmp_path)
    chain.append({"run_id": str(run_id), "event_type": "first"}, data_root=tmp_path)
    store = CheckpointStore(tmp_path / "runs")
    manifest = store.load(run_id)
    manifest["chain_tip"] = chain.GENESIS_HASH
    store.save(run_id, manifest)

    with pytest.raises(AuditChainError, match="chain_tip"):
        chain.append({"run_id": str(run_id), "event_type": "must-not-append"}, data_root=tmp_path)

    saved_manifest = store.load(run_id)
    assert saved_manifest["chain_tip"] == chain.GENESIS_HASH
    assert len((tmp_path / "runs" / str(run_id) / "AUDIT.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_verify_chain_cli_reports_valid_run(tmp_path, monkeypatch, capsys):
    run_id = _new_run(tmp_path)
    _append_entries(tmp_path, run_id, count=1)
    expected_tip = chain.tip(run_id, data_root=tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["aletheia", "verify-chain", str(run_id), "--data-dir", str(tmp_path)],
    )

    main()

    output = capsys.readouterr().out
    assert f"valid: {run_id}" in output
    assert expected_tip in output
    assert not (tmp_path / "benchmarks.sqlite3").exists()


def test_verify_chain_cli_returns_failure_for_tampered_run(tmp_path, monkeypatch, capsys):
    run_id = _new_run(tmp_path)
    _append_entries(tmp_path, run_id, count=2)
    audit_path = tmp_path / "runs" / str(run_id) / "AUDIT.jsonl"
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    entries[0]["event_type"] = "tampered-event"
    audit_path.write_text("".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["aletheia", "verify-chain", str(run_id), "--data-dir", str(tmp_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    output = capsys.readouterr().out
    assert "invalid" in output
    assert "1" in output
