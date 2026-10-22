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


# Result statuses written by adapters (``result.json``) mapped to the report's
# ``status`` vocabulary. Run 39120709419 showed why the results must be read
# back: every container had failed to start, yet the report called each adapter
# "ran" because nothing consulted them.
_RESULT_STATUS = {
    "ok": "ran",
    "succeeded": "ran",
    "success": "ran",
    "partial": "partial",
    "failed": "failed",
    "error": "failed",
}


def _result_detail(result: dict) -> str:
    """Copy the last non-empty stderr line — the error line for tracebacks."""
    lines = [
        line.strip()
        for line in str(result.get("stderr_tail") or "").splitlines()
        if line.strip()
    ]
    return lines[-1][:200] if lines else ""


def _adapter_summary(manifest: dict, run_dir: Path | None = None) -> list[dict]:
    """Every matching adapter with its outcome and its recorded skip reasons.

    Runs come from ``tools_invoked`` (which labels multi-seed invocations as
    ``adapter@seedN``); when ``run_dir`` is given the status is read back from
    each invocation's ``result.json`` so a failed container can never be
    reported as a successful run (run 39120709419). Skip records were persisted
    by ``resume`` from the adapters' own findings, so every listed reason is
    copied from adapter output, never inferred here.
    """
    skipped = manifest.get("skipped", [])
    summary: list[dict] = []
    for label in manifest.get("tools_invoked", []):
        adapter_name = label.split("@seed", 1)[0]
        entry: dict = {
            "adapter": adapter_name,
            "invocation": label,
            "status": "ran",
            "skipped_sources": [
                {"source": item.get("source", "unknown"), "reason": item.get("reason", "")}
                for item in skipped
                if item.get("adapter") == label
            ],
        }
        if run_dir is not None:
            result_path = run_dir / label / "result.json"
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                entry["status"] = "unknown"
                entry["detail"] = "result.json could not be read"
            else:
                entry["status"] = _RESULT_STATUS.get(
                    str(result.get("status")), str(result.get("status") or "unknown")
                )
                if entry["status"] != "ran":
                    entry["exit_code"] = result.get("exit_code")
                    detail = _result_detail(result)
                    if detail:
                        entry["detail"] = detail
        summary.append(entry)
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
        confirmed_links = list(getattr(self.resolver, "last_confirmed_links", []))
        adapter_summary = _adapter_summary(manifest, run_dir=self.checkpoints.run_dir(run_id))
        warnings = evaluate_jurisdiction_warnings(seeds=seeds, entities=graph.entities.values())
        self.graph_store.save_graph(str(run_id), graph.export())
        resolution_path = self.checkpoints.run_dir(run_id) / "resolution.json"
        resolution_payload = {
            "run_id": str(run_id),
            "candidate_count": len(candidates),
            "candidates": [c.to_dict() for c in candidates],
            "confirmed_link_count": len(confirmed_links),
            "confirmed_links": [link.to_dict() for link in confirmed_links],
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
            "confirmed_link_count": len(confirmed_links),
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
            request_meta={"candidate_count": len(candidates), "confirmed_link_count": len(confirmed_links), "jurisdiction_warning_count": len(warnings)},
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
