from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from aletheia.core.checkpoint import CheckpointStore
from aletheia.core.graph import Graph
from aletheia.core.models import ContextFilters, Seed
from aletheia.core.audit import AuditLogger
from aletheia.core.chain import AuditChainError, tip as audit_chain_tip, verify as verify_audit_chain
from aletheia.core.models import AuditEvent
from aletheia.core.warnings import evaluate_jurisdiction_warnings
from aletheia.phase2.reporting import generate_all_reports
from aletheia.phase2.resolution import EntityResolver
from aletheia.storage.file_store import FileGraphStore


def _adapter_summary(manifest: dict) -> list[dict]:
    """Every matching adapter with its outcome and its recorded skip reasons.

    Runs come from ``tools_invoked`` (which labels multi-seed invocations as
    ``adapter@seedN``); skip records were persisted by ``resume`` from the
    adapters' own findings, so every listed reason is copied from adapter
    output, never inferred here.
    """
    skipped = manifest.get("skipped", [])
    summary: list[dict] = []
    for label in manifest.get("tools_invoked", []):
        adapter_name = label.split("@seed", 1)[0]
        summary.append({
            "adapter": adapter_name,
            "invocation": label,
            "status": "ran",
            "skipped_sources": [
                {"source": item.get("source", "unknown"), "reason": item.get("reason", "")}
                for item in skipped
                if item.get("adapter") == label
            ],
        })
    for name in manifest.get("failed", []):
        summary.append({
            "adapter": name,
            "invocation": name,
            "status": "failed",
            "skipped_sources": [],
            "detail": "adapter raised during resume; see handoff and audit trail",
        })
    for name in manifest.get("pending", []):
        summary.append({
            "adapter": name,
            "invocation": name,
            "status": "not_run",
            "skipped_sources": [],
            "detail": "run incomplete: adapter still pending",
        })
    return summary


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
        seeds = [Seed.model_validate(raw) for raw in manifest["seeds"]]
        filters = (
            ContextFilters.model_validate(manifest["context_filters"])
            if manifest.get("context_filters")
            else None
        )
        candidates = self.resolver.resolve(graph, context_filters=filters)
        adapter_summary = _adapter_summary(manifest)
        warnings = evaluate_jurisdiction_warnings(seeds=seeds, entities=graph.entities.values())
        self.graph_store.save_graph(str(run_id), graph.export())
        resolution_path = self.checkpoints.run_dir(run_id) / "resolution.json"
        resolution_payload = {
            "run_id": str(run_id),
            "candidate_count": len(candidates),
            "candidates": [c.to_dict() for c in candidates],
        }
        resolution_path.write_text(json.dumps(resolution_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        seed = seeds[0]
        out_dir = self.checkpoints.run_dir(run_id) / "reports"
        artifacts = generate_all_reports(run_id=run_id, seed=seed, graph=graph, manifest=manifest,
                                         candidates=candidates, out_dir=out_dir,
                                         adapters=adapter_summary, warnings=warnings)
        manifest["phase"] = max(int(manifest.get("phase", 2)), 2)
        manifest["resolution"] = {
            "completed": True,
            "candidate_count": len(candidates),
            "artifact": str(resolution_path),
        }
        manifest["reports"] = {k: v for k, v in artifacts.items() if k in {"json", "pdf", "graphml", "stix2"}}
        manifest["report_hash"] = artifacts["content_hash_sha256"]
        manifest["jurisdiction_warning_count"] = len(warnings)
        current_phase = int(manifest.get("phase", 2))
        manifest["next_action"] = f"Review entity resolution and report artifacts for Phase {current_phase}."

        audit = AuditLogger(self.checkpoints.run_dir(run_id) / "AUDIT.jsonl")
        for warning in warnings:
            audit.log(AuditEvent(
                run_id=run_id,
                event_type="jurisdiction_warning",
                request_meta=warning.to_dict(),
                outcome="informational",
            ))
        audit.log(AuditEvent(
            run_id=run_id, event_type="phase2_finalize",
            request_meta={"candidate_count": len(candidates), "jurisdiction_warning_count": len(warnings)},
            outcome="succeeded",
        ))
        manifest["chain_tip"] = audit_chain_tip(run_id, data_root=self.data_root)
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
        return artifacts
