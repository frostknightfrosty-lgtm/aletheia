from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import UUID

from aletheia.core.models import ContextFilters, Seed
from aletheia.core.orchestrator import Orchestrator
from aletheia.phase7.benchmark import BenchmarkStore


class MCPServer:
    """Small stdio JSON-RPC bridge exposing Aletheia investigation and benchmark tools."""
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.orch = Orchestrator(data_root)
        self.bench = BenchmarkStore(data_root / "benchmarks.sqlite3")

    def tools(self) -> list[dict]:
        return [
            {"name":"investigate","description":"Create and run a legal-only Aletheia investigation. Pass seed for a single-seed run or seeds (a list of type:value strings) for a multi-seed investigation; context_filters narrow resolution where filtered attributes are recorded. Target-adjacent/personal-identifier adapters require an authorization assertion.","inputSchema":{"type":"object","properties":{"seed":{"type":"string"},"seeds":{"type":"array","items":{"type":"string"}},"authorization_assertion":{"type":"string"},"context_filters":{"type":"object","properties":{"country":{"type":"string"},"age_min":{"type":"integer","minimum":0,"maximum":120},"age_max":{"type":"integer","minimum":0,"maximum":120},"language":{"type":"string"},"timezone":{"type":"string"}}},"timeout_seconds":{"type":"integer","minimum":1,"maximum":3600}}}},
            {"name":"resume","description":"Resume a checkpointed Aletheia investigation.","inputSchema":{"type":"object","required":["run_id"],"properties":{"run_id":{"type":"string"},"authorization_assertion":{"type":"string"},"timeout_seconds":{"type":"integer","minimum":1,"maximum":3600}}}},
            {"name":"manifest","description":"Read an investigation checkpoint manifest.","inputSchema":{"type":"object","required":["run_id"],"properties":{"run_id":{"type":"string"}}}},
            {"name":"graph","description":"Read the persisted investigation graph.","inputSchema":{"type":"object","required":["run_id"],"properties":{"run_id":{"type":"string"}}}},
            {"name":"benchmark_leaderboard","description":"Read the labeled adapter benchmark leaderboard.","inputSchema":{"type":"object","properties":{}}},
        ]

    def call(self, name: str, args: dict) -> object:
        if name == "investigate":
            raw_seeds = args.get("seeds") or [args.get("seed")]
            if not raw_seeds or raw_seeds == [None]:
                raise ValueError("investigate requires seed or seeds")
            seeds = []
            for raw_seed in raw_seeds:
                kind, value = str(raw_seed).split(":", 1)
                seeds.append(Seed(type=kind, value=value))
            raw_filters = args.get("context_filters")
            context_filters = ContextFilters.model_validate(raw_filters) if raw_filters else None
            run_id=self.orch.create_run(seeds,legal_only=True,authorization_assertion=args.get("authorization_assertion"),context_filters=context_filters)
            self.orch.resume(run_id,authorization_assertion=args.get("authorization_assertion"),timeout_seconds=int(args.get("timeout_seconds",120)))
            return {"run_id":str(run_id),"status":"completed"}
        if name == "resume":
            run_id=UUID(args["run_id"]); self.orch.resume(run_id,authorization_assertion=args.get("authorization_assertion"),timeout_seconds=int(args.get("timeout_seconds",120)))
            return {"run_id":str(run_id),"status":"resumed"}
        if name == "manifest":
            data=self.orch.checkpoints.load(UUID(args["run_id"]))
            if data is None: raise ValueError("run not found")
            return data
        if name == "graph":
            import json as _json
            path=self.orch.graph_store.root/str(UUID(args["run_id"]))/"graph.json"
            if not path.exists(): raise ValueError("graph not found")
            return _json.loads(path.read_text(encoding="utf-8"))
        if name == "benchmark_leaderboard":
            return {"rows":self.bench.leaderboard()}
        raise ValueError(f"unknown tool: {name}")


def _response(req_id, result=None, error=None):
    payload={"jsonrpc":"2.0","id":req_id,"result":result} if error is None else {"jsonrpc":"2.0","id":req_id,"error":{"code":-32000,"message":str(error)}}
    print(json.dumps(payload,separators=(",",":")),flush=True)


def serve(data_root: Path) -> None:
    server=MCPServer(data_root)
    for line in sys.stdin:
        if not line.strip(): continue
        try:
            req=json.loads(line); method=req.get("method"); req_id=req.get("id")
            if method == "initialize":
                requested=(req.get("params") or {}).get("protocolVersion") or "2025-06-18"
                _response(req_id,{"protocolVersion":requested,"capabilities":{"tools":{}},"serverInfo":{"name":"aletheia","version":"0.7.0"}})
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                _response(req_id,{"tools":server.tools()})
            elif method == "tools/call":
                p=req.get("params") or {}; result=server.call(p.get("name"),p.get("arguments") or {})
                _response(req_id,{"content":[{"type":"text","text":json.dumps(result,indent=2,default=str)}],"isError":False})
            else:
                _response(req_id,error=f"unsupported method: {method}")
        except Exception as exc:
            _response(req_id if 'req_id' in locals() else None,error=exc)


def main() -> None:
    import os
    serve(Path(os.getenv("ALETHEIA_DATA_DIR", "./data")))


if __name__ == "__main__":
    main()
