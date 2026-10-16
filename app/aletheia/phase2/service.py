from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from aletheia.core.checkpoint import CheckpointStore
from aletheia.core.graph import Graph
from aletheia.core.models import Seed
from aletheia.core.audit import AuditLogger
from aletheia.core.chain import AuditChainError, verify as verify_audit_chain
from aletheia.core.models import AuditEvent
from aletheia.phase2.reporting import generate_all_reports
from aletheia.phase2.resolution import EntityResolver
from aletheia.storage.file_store import FileGraphStore


class Phase2Service:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.checkpoints = CheckpointStore(data_root / "runs")
        self.graph_store = FileGraphStore(data_root / "graphs")
        self.resolver = EntityResolver()

    def finalize(self, run_id: UUID) -> dict[str, str]:
        integrity = verify_audit_chain(run_id, data_root=self.data_root)
        if not integrity["valid"]:
            raise AuditChainError(
                f"run audit chain is invalid at sequence {integrity['first_broken_seq']}"
            )
        manifest = self.checkpoints.load(run_id)
        if manifest is None:
            raise FileNotFoundError(f"unknown run {run_id}")
        graph_path = self.graph_store.root / str(run_id) / "graph.json"
        if not graph_path.exists():
            raise FileNotFoundError(f"graph checkpoint missing for {run_id}")
        graph = Graph.from_export(json.loads(graph_path.read_text(encoding="utf-8")))
        candidates = self.resolver.resolve(graph)
        self.graph_store.save_graph(str(run_id), graph.export())
        resolution_path = self.checkpoints.run_dir(run_id) / "resolution.json"
        resolution_payload = {
            "run_id": str(run_id),
            "candidate_count": len(candidates),
            "candidates": [c.to_dict() for c in candidates],
        }
        resolution_path.write_text(json.dumps(resolution_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        seed = Seed.model_validate(manifest["seeds"][0])
        out_dir = self.checkpoints.run_dir(run_id) / "reports"
        artifacts = generate_all_reports(run_id=run_id, seed=seed, graph=graph, manifest=manifest,
                                         candidates=candidates, out_dir=out_dir)
        manifest["phase"] = max(int(manifest.get("phase", 2)), 2)
        manifest["resolution"] = {
            "completed": True,
            "candidate_count": len(candidates),
            "artifact": str(resolution_path),
        }
        manifest["reports"] = {k: v for k, v in artifacts.items() if k in {"json", "pdf", "graphml", "stix2"}}
        manifest["report_hash"] = artifacts["content_hash_sha256"]
        current_phase = int(manifest.get("phase", 2))
        manifest["next_action"] = f"Review entity resolution and report artifacts for Phase {current_phase}."
        self.checkpoints.save(run_id, manifest)
        self.checkpoints.write_handoff(
            run_id,
            manifest["goal"],
            manifest.get("completed", []) + ["Phase 2 entity resolution", "Phase 2 reports"],
            [f"Review entity resolution/report output for Phase {current_phase}; proceed to the next approved phase."],
            [str(self.checkpoints.manifest_path(run_id)), str(graph_path), str(resolution_path),
             *[str(Path(v)) for k, v in artifacts.items() if k in {"json", "pdf", "graphml", "stix2"}]],
            [],
            f"aletheia phase2 --run-id {run_id}",
        )
        AuditLogger(self.checkpoints.run_dir(run_id) / "AUDIT.jsonl").log(AuditEvent(
            run_id=run_id, event_type="phase2_finalize", request_meta={"candidate_count": len(candidates)},
            outcome="succeeded"
        ))
        return artifacts
