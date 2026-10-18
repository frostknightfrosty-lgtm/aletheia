from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

from aletheia.adapters.registry import phase7_adapters
from aletheia.core import egress
from aletheia.core.audit import AuditLogger
from aletheia.core.chain import AuditChainError, GENESIS_HASH, tip as audit_chain_tip
from aletheia.core.checkpoint import CheckpointStore
from aletheia.core.graph import Graph
from aletheia.core.models import AdapterRunRequest, AuditEvent, ContextFilters, Finding, Seed
from aletheia.storage.file_store import FileGraphStore
from aletheia.phase7.benchmark import BenchmarkStore


def workspace_label(adapter_name: str, seed_index: int, seed_count: int) -> str:
    """Workspace directory (and manifest label) for one adapter invocation.

    Single-seed runs keep the historical ``adapter`` directory name so existing
    artifacts are unchanged. Multi-seed runs use ``adapter@seedN`` (1-based) so
    every seed expansion owns a separate workspace and ``result.json``.
    """
    if seed_count <= 1:
        return adapter_name
    return f"{adapter_name}@seed{seed_index + 1}"


def extract_skipped_sources(findings: Sequence[Finding]) -> list[dict[str, str]]:
    """Collect adapter-recorded skip records from run findings.

    Composite adapters (and several single-source adapters) record each source
    they could not query as a finding carrying ``details.skipped = true`` with a
    ``reason`` — the missing-key and no-free-endpoint cases named in the project
    direction. This reads those records back so the router can persist them on
    the manifest and the report can list every skip with its reason.
    """
    skipped: list[dict[str, str]] = []
    for finding in findings:
        attributes = finding.attributes or {}
        details = attributes.get("details") if isinstance(attributes.get("details"), dict) else {}
        raw = attributes.get("raw_evidence") if isinstance(attributes.get("raw_evidence"), dict) else {}
        value = str(finding.value)
        is_skipped = (
            attributes.get("skipped") is True
            or details.get("skipped") is True
            or raw.get("skipped") is True
            or value.endswith(":skipped")
        )
        if not is_skipped:
            continue
        reason = (
            details.get("reason")
            or raw.get("reason")
            or attributes.get("skip_reason")
            or attributes.get("reason")
            or "reason not recorded by the adapter"
        )
        source = attributes.get("source")
        if source is None and value.endswith(":skipped"):
            source = value[: -len(":skipped")]
        skipped.append({"source": str(source or "unknown"), "reason": str(reason)})
    return skipped


class Orchestrator:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.checkpoints = CheckpointStore(data_root / "runs")
        self.graph_store = FileGraphStore(data_root / "graphs")
        self.adapters = phase7_adapters()
        self.benchmarks = BenchmarkStore(data_root / "benchmarks.sqlite3")

    def create_run(
        self,
        seeds: Seed | Sequence[Seed],
        legal_only: bool = True,
        authorization_assertion: str | None = None,
        context_filters: ContextFilters | None = None,
    ) -> UUID:
        """Create an investigation from one seed or a sequence of seeds.

        A single ``Seed`` keeps the original single-seed behavior. Given
        multiple seeds, every adapter that supports at least one seed is
        scheduled once per supported seed (``pending_seeds``); each seed expands
        as its own evidence tree, tagged onto findings via
        ``Provenance.seed_index``, and the resolver later runs the intersection
        pass over the trees.
        """
        seed_list = [seeds] if isinstance(seeds, Seed) else list(seeds)
        if not seed_list:
            raise ValueError("create_run requires at least one seed")
        if len(seed_list) == 1:
            goal = f"Aletheia investigation for {seed_list[0].type}:{seed_list[0].value}"
        else:
            goal = "Aletheia multi-seed investigation for " + ", ".join(
                f"{seed.type}:{seed.value}" for seed in seed_list
            )
        pending = [
            name
            for name, adapter in self.adapters.items()
            if any(adapter.supports(seed.type) for seed in seed_list)
        ]
        pending_seeds = {
            name: [
                index
                for index, seed in enumerate(seed_list)
                if self.adapters[name].supports(seed.type)
            ]
            for name in pending
        }
        run_id = uuid4()
        manifest = {
            "manifest_version": "0.7.0",
            "phase": 7,
            "status": "phase_7_built_pending_docker_integration",
            "goal": goal,
            "seeds": [seed.model_dump(mode="json") for seed in seed_list],
            "legal_only": legal_only,
            "authorization_assertion": authorization_assertion,
            "context_filters": context_filters.model_dump(mode="json") if context_filters is not None else None,
            "tools_invoked": [],
            "completed": [],
            "pending": pending,
            "pending_seeds": pending_seeds,
            "skipped": [],
            "failed": [],
            "next_action": None,
            "token_budget_remaining": None,
            "tool_versions": {name: a.descriptor.version_pin for name, a in self.adapters.items()},
            "chain_tip": GENESIS_HASH,
        }
        self.checkpoints.save(run_id, manifest)
        return run_id

    def resume(self, run_id: UUID, *, authorization_assertion: str | None = None, timeout_seconds: int = 120,
               proxy_url: str | None = None, wire_egress: bool = True,
               egress_rate: float = 1.0, egress_burst: float = 1.0) -> dict:
        """Run the pending adapter/seed invocations, routing network egress through the proxy.

        ``wire_egress`` defaults to ``True``: an adapter whose descriptor declares
        ``network_required=True`` runs on an ``--internal`` network with the proxy
        as its only way out. Pass ``False`` for offline replays and tests that must
        not touch Docker networking. ``egress_rate``/``egress_burst`` are the
        per-adapter proxy limits; the default 1 request/second is deliberately
        polite, and the proxy answers 429 rather than queueing, so raise them for
        wide sweeps (site-enumeration tools make hundreds of requests).

        Every resume records the lawful-basis declaration in the audit trail;
        an empty declaration is recorded as such and never blocks the run. Skip
        records (missing keys, retired endpoints) are persisted on the manifest
        so the Phase 2 report can list each skipped source with its reason.
        """
        manifest = self.checkpoints.load(run_id)
        if manifest is None:
            raise FileNotFoundError(f"unknown run {run_id}")
        seeds = [Seed.model_validate(raw) for raw in manifest["seeds"]]
        context_filters = (
            ContextFilters.model_validate(manifest["context_filters"]) if manifest.get("context_filters") else None
        )
        authorization_assertion = authorization_assertion or manifest.get("authorization_assertion")
        if authorization_assertion is not None:
            manifest["authorization_assertion"] = authorization_assertion
        audit = AuditLogger(self.checkpoints.run_dir(run_id) / "AUDIT.jsonl")
        audit.log(AuditEvent(
            run_id=run_id,
            event_type="lawful_basis_declaration",
            request_meta={
                "declared": bool(authorization_assertion),
                "assertion": authorization_assertion or "",
                "note": "optional declaration of lawful basis; an empty declaration does not stop a run",
            },
            outcome="recorded",
        ))
        graph_path = self.graph_store.root / str(run_id) / "graph.json"
        if graph_path.exists():
            import json
            graph = Graph.from_export(json.loads(graph_path.read_text(encoding="utf-8")))
        else:
            graph = Graph()

        pending = list(manifest.get("pending", []))
        pending_seeds = manifest.setdefault(
            "pending_seeds", {name: list(range(len(seeds))) for name in pending}
        )
        manifest.setdefault("skipped", [])
        manifest.setdefault("retry_counters", {})
        for adapter_name in pending:
            adapter = self.adapters[adapter_name]
            for seed_index in list(pending_seeds.get(adapter_name, list(range(len(seeds))))):
                seed = seeds[seed_index]
                label = workspace_label(adapter_name, seed_index, len(seeds))
                workspace_dir = self.checkpoints.run_dir(run_id) / label
                session = None
                adapter_proxy_url = proxy_url
                adapter_network = None
                if wire_egress and egress.is_wired(
                    adapter_name, network_required=adapter.descriptor.network_required
                ):
                    session = egress.ProxySession(
                        adapter_name, workspace_dir / "egress", rate=egress_rate, capacity=egress_burst
                    )
                    session.start()
                    adapter_proxy_url = session.proxy_url
                    adapter_network = session.network
                req = AdapterRunRequest(run_id=run_id, seed=seed, legal_only=manifest["legal_only"],
                                        authorization_assertion=authorization_assertion,
                                        timeout_seconds=timeout_seconds, proxy_url=adapter_proxy_url,
                                        network_name=adapter_network, seed_index=seed_index,
                                        context_filters=context_filters)
                try:
                    try:
                        result = adapter.run(req, workspace_dir, audit)
                    except AuditChainError:
                        raise
                    except Exception as exc:
                        manifest["retry_counters"][adapter_name] = manifest["retry_counters"].get(adapter_name, 0) + 1
                        if adapter_name not in manifest["failed"]:
                            manifest["failed"].append(adapter_name)
                        manifest["next_action"] = adapter_name
                        manifest["chain_tip"] = audit_chain_tip(run_id, data_root=self.data_root)
                        self.checkpoints.save(run_id, manifest)
                        self.checkpoints.write_handoff(
                            run_id,
                            manifest["goal"],
                            manifest["completed"],
                            [f"Retry adapter {adapter_name}"],
                            [str(self.checkpoints.manifest_path(run_id)), str(audit.path)],
                            [str(exc)],
                            f"aletheia resume --run-id {run_id}",
                        )
                        raise
                    # The proxy log records the adapter's egress; append it to the chain
                    # while the manifest anchor is still valid.
                    if session is not None:
                        entries = session.read_entries()
                        if entries:
                            egress.append_log_to_chain(run_id, entries, data_root=self.data_root)
                finally:
                    if session is not None:
                        session.stop()
                for finding in result.findings:
                    if len(seeds) > 1:
                        finding.provenance.seed_index = seed_index
                    graph.ingest(finding)
                for skip in extract_skipped_sources(result.findings):
                    record = {"adapter": label, **skip}
                    if record not in manifest["skipped"]:
                        manifest["skipped"].append(record)
                result_path = workspace_dir / "result.json"
                result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
                duration_ms = (result.finished_at - result.started_at).total_seconds() * 1000.0
                self.benchmarks.record_execution(adapter=adapter_name, duration_ms=duration_ms, status=result.status)
                manifest["tools_invoked"].append(label)
                pending_seeds[adapter_name].remove(seed_index)
                if not pending_seeds[adapter_name]:
                    if adapter_name in manifest.get("failed", []):
                        manifest["failed"].remove(adapter_name)
                    manifest["completed"].append(adapter_name)
                    manifest["pending"].remove(adapter_name)
                    pending_seeds.pop(adapter_name, None)
                manifest["next_action"] = manifest["pending"][0] if manifest["pending"] else None
                manifest["chain_tip"] = audit_chain_tip(run_id, data_root=self.data_root)
                self.graph_store.save_graph(str(run_id), graph.export())
                self.checkpoints.save(run_id, manifest)

        manifest["chain_tip"] = audit_chain_tip(run_id, data_root=self.data_root)
        self.checkpoints.save(run_id, manifest)
        self.checkpoints.write_handoff(
            run_id,
            manifest["goal"],
            manifest["completed"],
            ["Review benchmark leaderboard/UI/MCP surface; platform implementation checkpoint complete."],
            [str(self.checkpoints.manifest_path(run_id)), str(self.graph_store.root / str(run_id) / "graph.json")],
            [],
            f"aletheia resume --run-id {run_id}",
        )
        return manifest
