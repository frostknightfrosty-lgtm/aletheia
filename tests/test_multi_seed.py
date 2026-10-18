"""Tests for multi-seed investigations, the cross-seed intersection pass, and
context filters.

Everything runs against fake adapters and a ``tmp_path`` data root: no Docker
daemon and no network access are required.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from uuid import uuid4

from aletheia.core.adapters import Adapter
from aletheia.core.graph import Graph
from aletheia.core.models import (
    AdapterDescriptor,
    AdapterRunRequest,
    AdapterRunResult,
    ContextFilters,
    EntityType,
    Finding,
    Provenance,
    Seed,
    SeedType,
)
from aletheia.core.orchestrator import Orchestrator, extract_skipped_sources, workspace_label
from aletheia.phase2.resolution import EntityResolver


def _descriptor(name: str, seed_types: list[SeedType]) -> AdapterDescriptor:
    return AdapterDescriptor(
        name=name,
        license="project-internal",
        input_types=list(seed_types),
        output_types=[EntityType.USERNAME],
        legal_notes=[],
        rate_limit="n/a",
        invocation="test",
        version_pin="v1",
        upstream="https://example.invalid",
        network_required=False,
        docker_image="aletheia/test:v1",
    )


class _FakeAdapter(Adapter):
    """Records requests and returns configured findings per seed value."""

    def __init__(self, name: str, seed_types: list[SeedType], findings_for: dict | None = None,
                 skip_for: tuple[str, ...] = ()) -> None:
        self.descriptor = _descriptor(name, seed_types)
        self.requests: list[AdapterRunRequest] = []
        self._findings_for = findings_for or {}
        self._skip_for = set(skip_for)

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in self.descriptor.input_types

    def build_command(self, request, workspace):
        return ["runner.py"]

    def parse(self, request, workspace, stdout, stderr, exit_code):
        raise AssertionError("parse is not used by this test adapter")

    def run(self, request, workspace, audit):
        self.requests.append(request)
        workspace.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        findings = [
            Finding(
                entity_type=EntityType.USERNAME,
                value=value,
                provenance=Provenance(tool=self.descriptor.name, confidence=0.9, adapter_version="v1"),
            )
            for value in self._findings_for.get(request.seed.value, [])
        ]
        if request.seed.value in self._skip_for:
            findings.append(Finding(
                entity_type=EntityType.UNKNOWN,
                value="paid_api:skipped",
                attributes={"source": "paid_api", "details": {"skipped": True, "reason": "no free endpoint"}},
                provenance=Provenance(tool=self.descriptor.name, confidence=1.0, adapter_version="v1"),
            ))
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="ok",
            started_at=now,
            finished_at=now,
            findings=findings,
        )


def _load_graph(tmp_path, run_id) -> Graph:
    path = tmp_path / "graphs" / str(run_id) / "graph.json"
    return Graph.from_export(json.loads(path.read_text(encoding="utf-8")))


# -- scheduling ------------------------------------------------------------------


def test_create_run_multi_seed_schedules_each_adapter_per_supported_seed(tmp_path):
    orch = Orchestrator(tmp_path)
    orch.adapters = {
        "domain_only": _FakeAdapter("domain_only", [SeedType.DOMAIN]),
        "both": _FakeAdapter("both", [SeedType.DOMAIN, SeedType.EMAIL]),
    }
    run_id = orch.create_run([
        Seed(type=SeedType.DOMAIN, value="example.com"),
        Seed(type=SeedType.EMAIL, value="alice@example.com"),
    ])
    manifest = orch.checkpoints.load(run_id)
    assert manifest is not None
    assert manifest["goal"].startswith("Aletheia multi-seed investigation")
    assert [seed["type"] for seed in manifest["seeds"]] == ["domain", "email"]
    assert manifest["pending"] == ["domain_only", "both"]
    assert manifest["pending_seeds"] == {"domain_only": [0], "both": [0, 1]}
    assert manifest["skipped"] == []


def test_single_seed_run_keeps_legacy_shape_and_untagged_provenance(tmp_path):
    orch = Orchestrator(tmp_path)
    adapter = _FakeAdapter("both", [SeedType.DOMAIN], findings_for={"example.com": ["alice"]})
    orch.adapters = {"both": adapter}
    run_id = orch.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))
    manifest = orch.checkpoints.load(run_id)
    assert manifest["goal"] == "Aletheia investigation for domain:example.com"
    assert manifest["pending_seeds"] == {"both": [0]}

    orch.resume(run_id, wire_egress=False)

    manifest = orch.checkpoints.load(run_id)
    assert manifest["tools_invoked"] == ["both"]
    assert manifest["completed"] == ["both"] and manifest["pending"] == []
    graph = _load_graph(tmp_path, run_id)
    assert all(edge.provenance.seed_index is None for edge in graph.edges.values())


def test_resume_runs_each_adapter_once_per_supported_seed(tmp_path):
    orch = Orchestrator(tmp_path)
    adapter = _FakeAdapter("both", [SeedType.DOMAIN, SeedType.EMAIL], findings_for={
        "example.com": ["alice"],
        "alice@example.com": ["alice"],
    })
    orch.adapters = {"both": adapter}
    run_id = orch.create_run([
        Seed(type=SeedType.DOMAIN, value="example.com"),
        Seed(type=SeedType.EMAIL, value="alice@example.com"),
    ])

    orch.resume(run_id, wire_egress=False)

    assert [(r.seed.value, r.seed_index) for r in adapter.requests] == [
        ("example.com", 0),
        ("alice@example.com", 1),
    ]
    manifest = orch.checkpoints.load(run_id)
    assert manifest["tools_invoked"] == ["both@seed1", "both@seed2"]
    assert manifest["completed"] == ["both"] and manifest["pending"] == []
    graph = _load_graph(tmp_path, run_id)
    tagged = {
        edge.provenance.seed_index
        for edge in graph.edges.values()
        if edge.provenance.seed_index is not None
    }
    assert tagged == {0, 1}
    # Same value observed under both seeds lands on one entity with both trees.
    entity = next(e for e in graph.entities.values() if e.canonical_value == "alice")
    assert entity.entity_type == EntityType.USERNAME


def test_resume_persists_skip_records_on_the_manifest(tmp_path):
    orch = Orchestrator(tmp_path)
    orch.adapters = {"both": _FakeAdapter("both", [SeedType.DOMAIN], skip_for=("example.com",))}
    run_id = orch.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))

    orch.resume(run_id, wire_egress=False)

    manifest = orch.checkpoints.load(run_id)
    assert manifest["skipped"] == [
        {"adapter": "both", "source": "paid_api", "reason": "no free endpoint"}
    ]


def test_workspace_label_keeps_single_seed_directories(tmp_path):
    assert workspace_label("sherlock", 0, 1) == "sherlock"
    assert workspace_label("sherlock", 0, 2) == "sherlock@seed1"
    assert workspace_label("sherlock", 1, 2) == "sherlock@seed2"


def test_extract_skipped_sources_reads_adapter_skip_records():
    findings = [
        Finding(
            entity_type=EntityType.UNKNOWN,
            value="companies_house:skipped",
            attributes={"source": "companies_house", "details": {"skipped": True, "reason": "free key required"}},
            provenance=Provenance(tool="corporate_registry", confidence=0.8, adapter_version="1.0"),
        ),
        Finding(
            entity_type=EntityType.USERNAME,
            value="alice",
            provenance=Provenance(tool="sherlock", confidence=0.9, adapter_version="v1"),
        ),
    ]
    assert extract_skipped_sources(findings) == [
        {"source": "companies_house", "reason": "free key required"}
    ]


# -- intersection pass -----------------------------------------------------------


def _provenance(seed_index=None):
    return Provenance(tool="t", confidence=0.9, adapter_version="v1", seed_index=seed_index)


def test_cross_seed_corroboration_boosts_the_candidate_score():
    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice")
    graph.upsert_entity(EntityType.USERNAME, "alicee")
    graph.ingest(Finding(entity_type=EntityType.USERNAME, value="alice", provenance=_provenance(0)))
    graph.ingest(Finding(entity_type=EntityType.USERNAME, value="alicee", provenance=_provenance(0)))
    graph.ingest(Finding(entity_type=EntityType.USERNAME, value="alicee", provenance=_provenance(1)))

    candidates = EntityResolver(candidate_threshold=0.8).resolve(graph)

    assert len(candidates) == 1
    candidate = candidates[0]
    raw = round((0.65 * candidate.jaro_winkler) + (0.35 * candidate.levenshtein), 6)
    expected = min(1.0, round(raw * 1.05, 6))
    assert candidate.score == expected > raw
    explanation = "; ".join(candidate.explanation)
    assert "cross_seed_trees=0,1" in explanation
    assert f"cross_seed_boost={raw:.6f}->{expected:.6f}" in explanation
    assert "not calibrator output" in explanation


def test_single_tree_candidates_keep_the_raw_score():
    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice")
    graph.upsert_entity(EntityType.USERNAME, "alicee")
    graph.ingest(Finding(entity_type=EntityType.USERNAME, value="alice", provenance=_provenance(0)))
    graph.ingest(Finding(entity_type=EntityType.USERNAME, value="alicee", provenance=_provenance(0)))

    candidates = EntityResolver(candidate_threshold=0.8).resolve(graph)

    assert len(candidates) == 1
    candidate = candidates[0]
    raw = round((0.65 * candidate.jaro_winkler) + (0.35 * candidate.levenshtein), 6)
    assert candidate.score == raw
    assert "cross_seed_boost" not in "; ".join(candidate.explanation)


# -- context filters -------------------------------------------------------------


def test_country_filter_flags_positive_mismatches():
    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice", {"country": "United States (US)"})
    graph.upsert_entity(EntityType.USERNAME, "alicee", {"country": "United States (US)"})
    filters = ContextFilters(country="US")

    candidates = EntityResolver(candidate_threshold=0.8).resolve(graph, context_filters=filters)

    assert len(candidates) == 1
    assert candidates[0].decision == "candidate"
    assert "context_filters=no_conflict" in "; ".join(candidates[0].explanation)


def test_country_filter_excludes_the_pair_on_either_side():
    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice", {"country": "United States (US)"})
    graph.upsert_entity(EntityType.USERNAME, "alicee", {"country": "Germany"})
    filters = ContextFilters(country="US")

    candidates = EntityResolver(candidate_threshold=0.8).resolve(graph, context_filters=filters)

    assert len(candidates) == 1
    assert candidates[0].decision == "filtered_out"
    assert "context_filter_mismatch=" in "; ".join(candidates[0].explanation)


def test_entities_without_the_filtered_attribute_are_not_excluded():
    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice")
    graph.upsert_entity(EntityType.USERNAME, "alicee")
    filters = ContextFilters(country="DE")

    candidates = EntityResolver(candidate_threshold=0.8).resolve(graph, context_filters=filters)

    assert len(candidates) == 1
    assert candidates[0].decision == "candidate"


def test_age_filter_uses_computable_ages_only():
    graph = Graph()
    graph.upsert_entity(EntityType.PERSON, "alice smith", {"age": 70})
    graph.upsert_entity(EntityType.PERSON, "alice smyth", {"age": 30})

    candidates = EntityResolver(candidate_threshold=0.8).resolve(
        graph, context_filters=ContextFilters(age_max=40)
    )

    assert len(candidates) == 1
    assert candidates[0].decision == "filtered_out"
    assert "age 70 is above age_max 40" in "; ".join(candidates[0].explanation)


# -- report payload --------------------------------------------------------------


def test_report_payload_carries_multi_seed_fields():
    from aletheia.phase2.reporting import build_report_payload

    seed_a = Seed(type=SeedType.USERNAME, value="alice")
    seed_b = Seed(type=SeedType.EMAIL, value="alice@example.com")
    graph = Graph()
    graph.ingest(Finding(entity_type=EntityType.USERNAME, value="alice", provenance=_provenance(0)))
    graph.ingest(Finding(entity_type=EntityType.USERNAME, value="alice", provenance=_provenance(1)))
    candidates = EntityResolver().resolve(graph)
    manifest = {
        "goal": "multi",
        "legal_only": True,
        "seeds": [seed_a.model_dump(mode="json"), seed_b.model_dump(mode="json")],
        "context_filters": {"country": "gb"},
        "tool_versions": {},
    }

    payload = build_report_payload(
        run_id=uuid4(), seed=seed_a, graph=graph, manifest=manifest, candidates=candidates,
        adapters=[{"adapter": "x", "invocation": "x@seed1", "status": "ran", "skipped_sources": []}],
        warnings=[{"kind": "k", "subject": "s", "signal": "sig", "note": "n"}],
    )

    assert payload["statistics"]["seed_count"] == 2
    assert payload["statistics"]["cross_seed_entity_count"] == 1
    assert payload["context_filters"] == {"country": "gb"}
    assert payload["adapters"][0]["invocation"] == "x@seed1"
    assert payload["jurisdiction_warnings"][0]["kind"] == "k"


def test_adapter_summary_lists_runs_skips_and_pending():
    from aletheia.phase2.service import _adapter_summary

    manifest = {
        "tools_invoked": ["a", "b@seed2"],
        "skipped": [{"adapter": "b@seed2", "source": "paid", "reason": "no free endpoint"}],
        "failed": ["c"],
        "pending": ["d"],
    }

    summary = {entry["adapter"]: entry for entry in _adapter_summary(manifest)}

    assert summary["a"]["status"] == "ran" and summary["a"]["skipped_sources"] == []
    assert summary["b"]["status"] == "ran"
    assert summary["b"]["skipped_sources"] == [{"source": "paid", "reason": "no free endpoint"}]
    assert summary["c"]["status"] == "failed"
    assert summary["d"]["status"] == "not_run"


# -- CLI -------------------------------------------------------------------------


def test_cli_investigate_accepts_repeatable_seeds_and_filters(monkeypatch, tmp_path):
    from aletheia.cli import main as cli

    calls: list[dict] = []

    class _FakeOrchestrator:
        def __init__(self, data_dir):
            self.data_dir = data_dir

        def create_run(self, seeds, **kwargs):
            calls.append({"seeds": seeds, **kwargs})
            return uuid4()

        def resume(self, run_id, **kwargs):
            return {}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(sys, "argv", [
        "aletheia", "investigate",
        "--seed", "domain:example.com",
        "--seed", "email:alice@example.com",
        "--filter-country", "gb",
        "--filter-age-max", "70",
        "--data-dir", str(tmp_path),
    ])

    cli.main()

    run_call = calls[0]
    assert [(seed.type.value, seed.value) for seed in run_call["seeds"]] == [
        ("domain", "example.com"),
        ("email", "alice@example.com"),
    ]
    assert run_call["context_filters"].country == "gb"
    assert run_call["context_filters"].age_max == 70
