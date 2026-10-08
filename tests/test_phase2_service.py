import json
from uuid import uuid4
from pathlib import Path

from aletheia.core.checkpoint import CheckpointStore
from aletheia.core.graph import Graph
from aletheia.core.models import Seed, SeedType, Finding, EntityType, Provenance
from aletheia.phase2.service import Phase2Service


def test_phase2_finalize_updates_manifest_and_writes_artifacts(tmp_path):
    run_id = uuid4()
    data = tmp_path
    checkpoints = CheckpointStore(data / "runs")
    seed = Seed(type=SeedType.DOMAIN, value="example.com")
    checkpoints.save(run_id, {
        "goal": "phase2 test", "seeds": [seed.model_dump(mode="json")], "legal_only": True,
        "tools_invoked": ["theharvester"], "completed": ["theharvester"], "pending": [], "failed": [],
        "next_action": None, "token_budget_remaining": None, "tool_versions": {"theharvester": "4.11.1"}
    })
    g = Graph()
    p = Provenance(tool="theharvester", source_url="https://example.com", confidence=0.8, adapter_version="4.11.1")
    g.ingest(Finding(entity_type=EntityType.DOMAIN, value="Example.COM", provenance=p))
    graph_path = data / "graphs" / str(run_id) / "graph.json"
    graph_path.parent.mkdir(parents=True)
    graph_path.write_text(json.dumps(g.export(), indent=2))

    artifacts = Phase2Service(data).finalize(run_id)
    manifest = checkpoints.load(run_id)
    assert manifest["phase"] == 2
    assert manifest["resolution"]["completed"] is True
    assert Path(artifacts["pdf"]).exists()
    assert (checkpoints.run_dir(run_id) / "HANDOFF.md").exists()
