import json
from uuid import uuid4

from aletheia.core.graph import Graph
from aletheia.core.models import EntityType, Finding, Provenance, Seed, SeedType
from aletheia.phase2.reporting import build_report_payload, generate_all_reports
from aletheia.phase2.resolution import EntityResolver


def sample_graph():
    g = Graph()
    p1 = Provenance(tool="tool-a", source_url="https://source.example/a", confidence=0.8, adapter_version="1")
    p2 = Provenance(tool="tool-b", source_url="https://source.example/b", confidence=0.7, adapter_version="2")
    g.ingest(Finding(entity_type=EntityType.DOMAIN, value="Example.COM", provenance=p1))
    g.ingest(Finding(entity_type=EntityType.DOMAIN, value="example.com.", provenance=p2))
    return g


def test_report_has_provenance_and_stable_content_hash():
    g = sample_graph()
    candidates = EntityResolver().resolve(g)
    payload = build_report_payload(
        run_id=uuid4(), seed=Seed(type=SeedType.DOMAIN, value="example.com"), graph=g,
        manifest={"goal": "test", "legal_only": True, "checkpoint_hash": "abc", "tool_versions": {"a": "1"}},
        candidates=candidates,
    )
    assert payload["claims"][0]["evidence"]
    assert payload["content_hash_sha256"]
    assert payload["statistics"]["entity_count"] == 1


def test_all_report_formats_emit(tmp_path):
    g = sample_graph()
    candidates = EntityResolver().resolve(g)
    artifacts = generate_all_reports(
        run_id=uuid4(), seed=Seed(type=SeedType.DOMAIN, value="example.com"), graph=g,
        manifest={"goal": "test", "legal_only": True, "checkpoint_hash": "abc", "tool_versions": {}},
        candidates=candidates, out_dir=tmp_path,
    )
    for key in ("json", "pdf", "graphml", "stix2"):
        path = tmp_path / __import__('pathlib').Path(artifacts[key]).name
        assert path.exists() and path.stat().st_size > 0
    data = json.loads((tmp_path / "report.json").read_text())
    assert data["artifact_sha256"]["report.pdf"] == artifacts["pdf_sha256"]
