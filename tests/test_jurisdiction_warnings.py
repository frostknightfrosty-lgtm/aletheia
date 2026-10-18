"""Tests for the informational jurisdiction warnings.

The warnings implement the sensitive-behavior requirement from the project
direction: they never gate a run, they are recorded in the audit trail and the
report, and the recorded signal says exactly what matched.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from aletheia.core.checkpoint import CheckpointStore
from aletheia.core.chain import verify as verify_audit_chain
from aletheia.core.graph import Graph
from aletheia.core.models import EntityType, Finding, Provenance, Seed, SeedType
from aletheia.core.warnings import (
    KIND_HEALTH_DATA,
    KIND_MINOR,
    KIND_PRIVACY_JURISDICTION,
    KIND_PROTECTED_CLASS,
    WARNING_NOTE,
    evaluate_jurisdiction_warnings,
)
from aletheia.phase2.service import Phase2Service


def test_privacy_jurisdiction_and_minor_entity_signals():
    graph = Graph()
    graph.upsert_entity(EntityType.PERSON, "Jane Doe", {"country": "Germany", "birth_year": 2015})

    warnings = evaluate_jurisdiction_warnings(
        seeds=[Seed(type=SeedType.NAME, value="Jane Doe")],
        entities=graph.entities.values(),
    )

    kinds = {warning.kind for warning in warnings}
    assert KIND_PRIVACY_JURISDICTION in kinds
    assert KIND_MINOR in kinds
    signals = " ".join(warning.signal for warning in warnings)
    assert "attribute:country=Germany" in signals
    assert any(warning.signal.startswith("computed_age=") for warning in warnings)
    assert all(warning.note == WARNING_NOTE for warning in warnings)


def test_health_and_protected_class_signals():
    graph = Graph()
    graph.upsert_entity(EntityType.COMPANY, "Acme Clinic", {"industry": "healthcare", "religion": "hinduism"})

    warnings = evaluate_jurisdiction_warnings(entities=graph.entities.values())

    kinds = {warning.kind for warning in warnings}
    assert KIND_HEALTH_DATA in kinds
    assert KIND_PROTECTED_CLASS in kinds


def test_seed_value_privacy_jurisdiction_signal():
    warnings = evaluate_jurisdiction_warnings(
        seeds=[Seed(type=SeedType.GEOLOCATION, value="France")]
    )

    assert [(warning.kind, warning.subject) for warning in warnings] == [
        (KIND_PRIVACY_JURISDICTION, "seed:0")
    ]


def test_warning_signals_are_deduplicated():
    graph = Graph()
    graph.upsert_entity(EntityType.PERSON, "X", {"country": ["Germany", "Germany"]})

    warnings = evaluate_jurisdiction_warnings(entities=graph.entities.values())

    assert len([warning for warning in warnings if warning.kind == KIND_PRIVACY_JURISDICTION]) == 1


def test_phase2_reports_and_audits_warnings(tmp_path):
    run_id = uuid4()
    checkpoints = CheckpointStore(tmp_path / "runs")
    seed = Seed(type=SeedType.NAME, value="Jane Doe")
    checkpoints.save(run_id, {
        "goal": "warnings test", "seeds": [seed.model_dump(mode="json")], "legal_only": True,
        "tools_invoked": ["social_profile"], "completed": ["social_profile"], "pending": [], "failed": [],
        "next_action": None, "token_budget_remaining": None, "tool_versions": {},
    })
    graph = Graph()
    graph.ingest(Finding(
        entity_type=EntityType.PERSON,
        value="Jane Doe",
        attributes={"country": "Germany"},
        provenance=Provenance(tool="social_profile", confidence=0.7, adapter_version="v1"),
    ))
    graph_path = tmp_path / "graphs" / str(run_id) / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph.export(), indent=2), encoding="utf-8")
    # A completed adapter always has a result.json in a real run; the report
    # now reads the invocation status back from it (run 39120709419).
    result_dir = checkpoints.run_dir(run_id) / "social_profile"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "result.json").write_text(
        json.dumps({"status": "succeeded", "exit_code": 0, "stderr_tail": ""}), encoding="utf-8")

    artifacts = Phase2Service(tmp_path).finalize(run_id)

    report = json.loads(Path(artifacts["json"]).read_text(encoding="utf-8"))
    assert report["jurisdiction_warnings"]
    assert report["adapters"] == [{
        "adapter": "social_profile",
        "invocation": "social_profile",
        "status": "ran",
        "skipped_sources": [],
    }]
    manifest = checkpoints.load(run_id)
    assert manifest["jurisdiction_warning_count"] == len(report["jurisdiction_warnings"])
    assert verify_audit_chain(run_id, data_root=tmp_path)["valid"] is True
