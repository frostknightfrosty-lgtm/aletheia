from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from aletheia.core import chain
from aletheia.core.models import ContextFilters, Seed, SeedType
from aletheia.core.orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aletheia")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("investigate")
    inv.add_argument("--seed", required=True, action="append", help="type:value, e.g. username:alice, email:alice@example.com, phone:+14155552671, domain:example.com, url:https://example.com/profile, or name:Acme Corporation. Repeat --seed for a multi-seed investigation.")
    inv.add_argument("--legal-only", action="store_true", default=True)
    inv.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    inv.add_argument("--timeout", type=int, default=120)
    inv.add_argument("--proxy", default=os.getenv("ALETHEIA_HTTP_PROXY") or None)
    inv.add_argument("--no-egress-proxy", action="store_true", help="run network adapters without the egress proxy (offline replays only)")
    inv.add_argument("--authorization-assertion", default=None, help="Explicit authorization statement required for target-adjacent or personal-identifier lookups")
    inv.add_argument("--filter-country", default=None, help="constraint filter: match recorded country/jurisdiction attributes (token match)")
    inv.add_argument("--filter-age-min", type=int, default=None, help="constraint filter: minimum age (compared where an age is computable)")
    inv.add_argument("--filter-age-max", type=int, default=None, help="constraint filter: maximum age (compared where an age is computable)")
    inv.add_argument("--filter-language", default=None, help="constraint filter: match recorded language attributes (token match)")
    inv.add_argument("--filter-timezone", default=None, help="constraint filter: match recorded IANA timezone attributes")
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
    resume.add_argument("--no-egress-proxy", action="store_true", help="run network adapters without the egress proxy (offline replays only)")
    resume.add_argument("--authorization-assertion", default=None, help="Explicit authorization statement; stored with the run for exact resumability")
    verify_chain = sub.add_parser("verify-chain", help="verify a run's hash-chained audit log")
    verify_chain.add_argument("run_id", type=UUID)
    verify_chain.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))

    storage = sub.add_parser("storage", help="inspect and populate Phase-14 storage backends")
    storage_sub = storage.add_subparsers(dest="storage_cmd", required=True)
    from aletheia.storage import BACKENDS as _BACKENDS

    storage_health = storage_sub.add_parser("health", help="probe each configured backend")
    storage_health.add_argument("--backend", default=None, choices=sorted(_BACKENDS))
    storage_health.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))

    storage_migrate = storage_sub.add_parser("migrate", help="apply pending schema migrations")
    storage_migrate.add_argument("--backend", required=True, choices=sorted(_BACKENDS))
    storage_migrate.add_argument("--target", default=None, help="override the backend DSN/path")
    storage_migrate.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))

    storage_sync = storage_sub.add_parser("sync", help="copy a run's graph and manifest into a backend")
    storage_sync.add_argument("--run-id", required=True, type=UUID)
    storage_sync.add_argument("--backend", required=True, choices=sorted(_BACKENDS))
    storage_sync.add_argument("--target", default=None, help="override the backend DSN/path")
    storage_sync.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    return parser


def parse_seed(raw: str) -> Seed:
    try:
        kind, value = raw.split(":", 1)
        return Seed(type=SeedType(kind), value=value)
    except ValueError as exc:
        raise SystemExit("Seed must be formatted type:value") from exc


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "verify-chain":
        result = chain.verify(args.run_id, data_root=Path(args.data_dir))
        if result["valid"]:
            print(f"valid: {args.run_id}")
            print(f"chain tip: {result['tip_hash']}")
            print("manifest anchor: verified" if result["anchored"] else "manifest anchor: unavailable")
        else:
            print(f"invalid: {args.run_id}")
            print(f"first broken seq: {result['first_broken_seq']}")
            print(f"chain tip: {result['tip_hash']}")
            if result.get("error"):
                print(f"reason: {result['error']}")
            raise SystemExit(1)
    elif args.cmd == "investigate":
        orch = Orchestrator(Path(args.data_dir))
        seeds = [parse_seed(raw) for raw in args.seed]
        filters = None
        if any(value is not None for value in (args.filter_country, args.filter_age_min, args.filter_age_max,
                                               args.filter_language, args.filter_timezone)):
            filters = ContextFilters(country=args.filter_country, age_min=args.filter_age_min,
                                     age_max=args.filter_age_max, language=args.filter_language,
                                     timezone=args.filter_timezone)
        run_id = orch.create_run(seeds, legal_only=True, authorization_assertion=args.authorization_assertion,
                                 context_filters=filters)
        print(run_id)
        orch.resume(run_id, authorization_assertion=args.authorization_assertion, timeout_seconds=args.timeout,
                    proxy_url=args.proxy, wire_egress=not args.no_egress_proxy)
        print(f"completed: {run_id}")
    elif args.cmd == "phase2":
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
            print(json.dumps(BenchmarkStore(Path(args.data_dir) / "benchmarks.sqlite3").leaderboard(), indent=2))
    elif args.cmd == "mcp-server":
        from aletheia.mcp.server import serve
        serve(Path(args.data_dir))
    elif args.cmd == "resume":
        orch = Orchestrator(Path(args.data_dir))
        orch.resume(UUID(args.run_id), authorization_assertion=args.authorization_assertion,
                    timeout_seconds=args.timeout, proxy_url=args.proxy,
                    wire_egress=not args.no_egress_proxy)
        print(f"resumed: {args.run_id}")
    elif args.cmd == "storage":
        from aletheia import storage as storage_mod
        from aletheia.storage.base import MigrationRunner

        if args.storage_cmd == "health":
            names = [args.backend] if args.backend else None
            print(json.dumps(storage_mod.health_report(names, data_dir=Path(args.data_dir)), indent=2))
        else:
            backend = storage_mod.resolve_backend(args.backend, Path(args.data_dir), args.target)
            try:
                if args.storage_cmd == "migrate":
                    print(json.dumps(MigrationRunner(backend).run(), indent=2))
                else:
                    print(json.dumps(storage_mod.sync_run(backend, args.run_id, Path(args.data_dir)), indent=2))
            finally:
                backend.close()

if __name__ == "__main__":
    main()
