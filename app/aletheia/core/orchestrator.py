from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from aletheia.adapters.registry import phase7_adapters
from aletheia.core import egress
from aletheia.core.audit import AuditLogger
from aletheia.core.chain import AuditChainError, GENESIS_HASH, tip as audit_chain_tip
from aletheia.core.checkpoint import CheckpointStore
from aletheia.core.graph import Graph
from aletheia.core.models import AdapterRunRequest, Seed
from aletheia.storage.file_store import FileGraphStore
from aletheia.phase7.benchmark import BenchmarkStore


class Orchestrator:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.checkpoints = CheckpointStore(data_root / "runs")
        self.graph_store = FileGraphStore(data_root / "graphs")
        self.adapters = phase7_adapters()
        self.benchmarks = BenchmarkStore(data_root / "benchmarks.sqlite3")

    def create_run(self, seed: Seed, legal_only: bool = True, authorization_assertion: str | None = None) -> UUID:
        run_id = uuid4()
        manifest = {
            "manifest_version": "0.7.0",
            "phase": 7,
            "status": "phase_7_built_pending_docker_integration",
            "goal": f"Aletheia investigation for {seed.type}:{seed.value}",
            "seeds": [seed.model_dump(mode="json")],
            "legal_only": legal_only,
            "authorization_assertion": authorization_assertion,
            "tools_invoked": [],
            "completed": [],
            "pending": [name for name, a in self.adapters.items() if a.supports(seed.type)],
            "failed": [],
            "next_action": None,
            "token_budget_remaining": None,
            "tool_versions": {name: a.descriptor.version_pin for name, a in self.adapters.items()},
            "chain_tip": GENESIS_HASH,
        }
        self.checkpoints.save(run_id, manifest)
        return run_id

    def resume(self, run_id: UUID, *, authorization_assertion: str | None = None, timeout_seconds: int = 120,
               proxy_url: str | None = None, wire_egress: bool = False) -> dict:
        manifest = self.checkpoints.load(run_id)
        if manifest is None:
            raise FileNotFoundError(f"unknown run {run_id}")
        seed = Seed.model_validate(manifest["seeds"][0])
        authorization_assertion = authorization_assertion or manifest.get("authorization_assertion")
        if authorization_assertion is not None:
            manifest["authorization_assertion"] = authorization_assertion
        audit = AuditLogger(self.checkpoints.run_dir(run_id) / "AUDIT.jsonl")
        graph_path = self.graph_store.root / str(run_id) / "graph.json"
        if graph_path.exists():
            import json
            graph = Graph.from_export(json.loads(graph_path.read_text(encoding="utf-8")))
        else:
            graph = Graph()

        pending = list(manifest.get("pending", []))
        manifest.setdefault("retry_counters", {})
        for adapter_name in pending:
            adapter = self.adapters[adapter_name]
            session = None
            adapter_proxy_url = proxy_url
            adapter_network = None
            if wire_egress and egress.is_wired(adapter_name):
                session = egress.ProxySession(
                    adapter_name, self.checkpoints.run_dir(run_id) / adapter_name / "egress"
                )
                session.start()
                adapter_proxy_url = session.proxy_url
                adapter_network = session.network
            req = AdapterRunRequest(run_id=run_id, seed=seed, legal_only=manifest["legal_only"],
                                    authorization_assertion=authorization_assertion,
                                    timeout_seconds=timeout_seconds, proxy_url=adapter_proxy_url,
                                    network_name=adapter_network)
            try:
                try:
                    result = adapter.run(req, self.checkpoints.run_dir(run_id) / adapter_name, audit)
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
                graph.ingest(finding)
            result_path = self.checkpoints.run_dir(run_id) / adapter_name / "result.json"
            result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            duration_ms = (result.finished_at - result.started_at).total_seconds() * 1000.0
            self.benchmarks.record_execution(adapter=adapter_name, duration_ms=duration_ms, status=result.status)
            manifest["tools_invoked"].append(adapter_name)
            if adapter_name in manifest.get("failed", []):
                manifest["failed"].remove(adapter_name)
            manifest["completed"].append(adapter_name)
            manifest["pending"].remove(adapter_name)
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
