from __future__ import annotations

import argparse
import os
from pathlib import Path

from aletheia.core.models import Seed, SeedType
from aletheia.core.orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aletheia")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("investigate")
    inv.add_argument("--seed", required=True, help="type:value, e.g. username:alice, email:alice@example.com, phone:+14155552671, domain:example.com, url:https://example.com/profile, or name:Acme Corporation")
    inv.add_argument("--legal-only", action="store_true", default=True)
    inv.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    inv.add_argument("--timeout", type=int, default=120)
    inv.add_argument("--proxy", default=os.getenv("ALETHEIA_HTTP_PROXY") or None)
    inv.add_argument("--authorization-assertion", default=None, help="Explicit authorization statement required for target-adjacent or personal-identifier lookups")
    phase2 = sub.add_parser("phase2", help="resolve entities and emit Phase 2 reports")
    phase2.add_argument("--run-id", required=True)
    phase2.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))

    bench = sub.add_parser("benchmark", help="record/list labeled adapter benchmark cases")
    bench_sub = bench.add_subparsers(dest="benchmark_cmd", required=True)
    bench_record = bench_sub.add_parser("record")
    bench_record.add_argument("--adapter", required=True)
    bench_record.add_argument("--seed", required=True)
    bench_record.add_argument("--expected", default="", help="comma-separated canonical observations")
    bench_record.add_argument("--observed", default="", help="comma-separated canonical observations")
    bench_record.add_argument("--duration-ms", type=float, required=True)
    bench_record.add_argument("--negative-count", type=int, default=None)
    bench_record.add_argument("--cost", type=float, default=None)
    bench_record.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    bench_list = bench_sub.add_parser("leaderboard")
    bench_list.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))

    mcp = sub.add_parser("mcp-server", help="run the local Aletheia MCP stdio server")
    mcp.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))

    resume = sub.add_parser("resume")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    resume.add_argument("--timeout", type=int, default=120)
    resume.add_argument("--proxy", default=os.getenv("ALETHEIA_HTTP_PROXY") or None)
    resume.add_argument("--authorization-assertion", default=None, help="Explicit authorization statement; stored with the run for exact resumability")
    return parser


def parse_seed(raw: str) -> Seed:
    try:
        kind, value = raw.split(":", 1)
        return Seed(type=SeedType(kind), value=value)
    except ValueError as exc:
        raise SystemExit("Seed must be formatted type:value") from exc


def main() -> None:
    args = build_parser().parse_args()
    orch = Orchestrator(Path(args.data_dir))
    if args.cmd == "investigate":
        seed = parse_seed(args.seed)
        run_id = orch.create_run(seed, legal_only=True, authorization_assertion=args.authorization_assertion)
        print(run_id)
        orch.resume(run_id, authorization_assertion=args.authorization_assertion, timeout_seconds=args.timeout, proxy_url=args.proxy)
        print(f"completed: {run_id}")
    elif args.cmd == "phase2":
        from uuid import UUID
        from aletheia.phase2.service import Phase2Service
        artifacts = Phase2Service(Path(args.data_dir)).finalize(UUID(args.run_id))
        for key, value in artifacts.items():
            print(f"{key}={value}")
    elif args.cmd == "benchmark":
        from aletheia.phase7.benchmark import BenchmarkStore
        if args.benchmark_cmd == "record":
            raw_kind, raw_value = args.seed.split(":", 1)
            store = BenchmarkStore(Path(args.data_dir) / "benchmarks.sqlite3")
            cid = store.record(adapter=args.adapter, seed_type=raw_kind, seed_value=raw_value,
                               expected=[x for x in args.expected.split(",") if x],
                               observed=[x for x in args.observed.split(",") if x],
                               duration_ms=args.duration_ms, negative_count=args.negative_count, cost=args.cost)
            print(cid)
        else:
            import json
            print(json.dumps(BenchmarkStore(Path(args.data_dir) / "benchmarks.sqlite3").leaderboard(), indent=2))
    elif args.cmd == "mcp-server":
        from aletheia.mcp.server import serve
        serve(Path(args.data_dir))
    elif args.cmd == "resume":
        from uuid import UUID
        orch.resume(UUID(args.run_id), authorization_assertion=args.authorization_assertion, timeout_seconds=args.timeout, proxy_url=args.proxy)
        print(f"resumed: {args.run_id}")

if __name__ == "__main__":
    main()
