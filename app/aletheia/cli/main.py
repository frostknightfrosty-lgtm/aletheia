from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
from pathlib import Path
from uuid import UUID

from aletheia.core import chain
from aletheia.core.models import ContextFilters, Seed, SeedType
from aletheia.core.orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aletheia")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("investigate")
    inv.add_argument("--seed", required=True, action="append", help="type:value, e.g. username:alice, email:alice@example.com, phone:+14155552671, domain:example.com, url:https://example.com/profile, name:Acme Corporation, or hashtag:osint. Repeat --seed for a multi-seed investigation.")
    inv.add_argument("--legal-only", action="store_true", default=True)
    inv.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    inv.add_argument("--timeout", type=int, default=120)
    inv.add_argument("--proxy", default=os.getenv("ALETHEIA_HTTP_PROXY") or None)
    inv.add_argument("--no-egress-proxy", action="store_true", help="run network adapters without the egress proxy (offline replays only)")
    inv.add_argument("--egress-rate", type=float, default=1.0, help="per-adapter egress proxy limit: sustained requests/second (default 1; the proxy answers 429 over the limit)")
    inv.add_argument("--egress-burst", type=float, default=1.0, help="per-adapter egress proxy limit: burst capacity (default 1)")
    inv.add_argument("--authorization-assertion", default=None, help="Explicit authorization statement required for target-adjacent or personal-identifier lookups")
    inv.add_argument("--filter-country", default=None, help="constraint filter: match recorded country/jurisdiction attributes (token match)")
    inv.add_argument("--filter-age-min", type=int, default=None, help="constraint filter: minimum age (compared where an age is computable)")
    inv.add_argument("--filter-age-max", type=int, default=None, help="constraint filter: maximum age (compared where an age is computable)")
    inv.add_argument("--filter-language", default=None, help="constraint filter: match recorded language attributes (token match)")
    inv.add_argument("--filter-timezone", default=None, help="constraint filter: match recorded IANA timezone attributes")

    ask = sub.add_parser(
        "ask",
        help="parse a free-text question, run the pivot cascade, and generate a local-LLM dossier",
    )
    ask.add_argument("query", help='e.g. "Find the person behind username frost2233"')
    ask.add_argument("--fixture", default=None, help="fixture observer JSON for a network-free dry-run")
    ask.add_argument("--authorization-assertion", default=None, help="Explicit authorization statement; stored verbatim on the run manifest")
    ask.add_argument("--case-id", default=None, type=UUID, help="record the run on this case (P17.7 case memory)")
    ask.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    ask.add_argument("--timeout", type=int, default=120)
    ask.add_argument("--proxy", default=os.getenv("ALETHEIA_HTTP_PROXY") or None)
    ask.add_argument("--no-egress-proxy", action="store_true", help="run network adapters without the egress proxy (offline replays only)")
    ask.add_argument("--egress-rate", type=float, default=1.0, help="per-adapter egress proxy limit: sustained requests/second (default 1)")
    ask.add_argument("--egress-burst", type=float, default=1.0, help="per-adapter egress proxy limit: burst capacity (default 1)")
    ask.add_argument("--max-expansions", type=int, default=None, help="hard budget on pivot expansions (default: uncapped)")
    ask.add_argument("--owner-mode", action="store_true", help="owner mode: depth escalation to 5 once HARD evidence is seen")
    ask.add_argument("--llm-url", default=os.getenv("ALETHEIA_LLM_URL", "http://localhost:11434/v1"), help="OpenAI-compatible endpoint (default: local Ollama)")
    ask.add_argument("--llm-model", default=os.getenv("ALETHEIA_LLM_MODEL", "llama3"), help="local model name (default: llama3)")
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
    resume.add_argument("--egress-rate", type=float, default=1.0, help="per-adapter egress proxy limit: sustained requests/second (default 1; the proxy answers 429 over the limit)")
    resume.add_argument("--egress-burst", type=float, default=1.0, help="per-adapter egress proxy limit: burst capacity (default 1)")
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

    cascade = sub.add_parser("cascade", help="Phase 17 cascade tools: run, review, confirm, purge")
    cascade.add_argument("--interactive", action="store_true", help="pause on SAME_AS_CANDIDATE edges in the 0.70-0.85 review band and record the operator's labels")
    cascade_sub = cascade.add_subparsers(dest="cascade_cmd", required=True)
    cascade_run = cascade_sub.add_parser("run", help="run the pivot cascade (fixture dry-run or live adapters) and write its artifacts")
    cascade_run.add_argument("--seed", required=True, action="append", help="type:value; repeat for a multi-seed cascade")
    cascade_run.add_argument("--fixture", default=None, help="fixture observer JSON for a network-free dry-run")
    cascade_run.add_argument("--authorization-assertion", default=None, help="Explicit authorization statement; stored verbatim on the run manifest")
    cascade_run.add_argument("--case-id", default=None, type=UUID, help="record the run on this case (P17.7 case memory)")
    cascade_run.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    cascade_run.add_argument("--timeout", type=int, default=120)
    cascade_run.add_argument("--proxy", default=os.getenv("ALETHEIA_HTTP_PROXY") or None)
    cascade_run.add_argument("--no-egress-proxy", action="store_true", help="run network adapters without the egress proxy (offline replays only)")
    cascade_run.add_argument("--egress-rate", type=float, default=1.0, help="per-adapter egress proxy limit: sustained requests/second (default 1; the proxy answers 429 over the limit)")
    cascade_run.add_argument("--egress-burst", type=float, default=1.0, help="per-adapter egress proxy limit: burst capacity (default 1)")
    cascade_run.add_argument("--max-expansions", type=int, default=None, help="hard budget on pivot expansions (default: uncapped)")
    cascade_run.add_argument("--owner-mode", action="store_true", help="owner mode: depth escalation to 5 once HARD evidence is seen")
    cascade_run.add_argument("--interactive", action="store_true", default=argparse.SUPPRESS, help="pause on SAME_AS_CANDIDATE edges in the 0.70-0.85 review band")
    cascade_run.add_argument("--calibration-pairs", default=None, help="path to append human-labelled pairs (default: tests/fixtures/calibration_pairs.json)")
    cascade_review = cascade_sub.add_parser("review", help="replay a decision ledger and verify its hash chain")
    cascade_review.add_argument("--ledger", required=True, help="path to the decision ledger (JSONL records or a JSON list)")
    cascade_review.add_argument("--kinds", default=None, help="comma-separated kinds to show, e.g. pivot_granted,stop")
    cascade_confirm = cascade_sub.add_parser("confirm", help="record a confirmation label (mine/not-mine/unsure) for a cluster")
    cascade_confirm.add_argument("--case-id", required=True)
    cascade_confirm.add_argument("--cluster-id", required=True)
    cascade_confirm.add_argument("--label", required=True, choices=["mine", "not_mine", "unsure"])
    cascade_confirm.add_argument("--score", type=float, default=None, help="the cluster's recorded score, when one exists (never invented)")
    cascade_confirm.add_argument("--note", default="")
    cascade_confirm.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    cascade_purge = cascade_sub.add_parser("purge", help="delete a case's artifacts (case file + its labels) on request")
    cascade_purge.add_argument("--case-id", required=True, type=UUID)
    cascade_purge.add_argument("--data-dir", default=os.getenv("ALETHEIA_DATA_DIR", "./data"))
    return parser


def parse_seed(raw: str) -> Seed:
    try:
        kind, value = raw.split(":", 1)
        return Seed(type=SeedType(kind), value=value)
    except ValueError as exc:
        raise SystemExit("Seed must be formatted type:value") from exc


_QUERY_SEED_TYPES = {
    "account": SeedType.USERNAME,
    "company": SeedType.COMPANY_NAME,
    "handle": SeedType.USERNAME,
    "user": SeedType.USERNAME,
}
_QUERY_STOPWORDS = {
    "a",
    "account",
    "an",
    "and",
    "behind",
    "for",
    "handle",
    "identity",
    "is",
    "of",
    "person",
    "profile",
    "the",
    "this",
    "user",
    "username",
    "who",
}
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DOMAIN_RE = re.compile(
    r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\b"
)
_PHONE_RE = re.compile(r"(?<![\w.])(\+?\d[\d().\s-]{6,}\d)(?![\w.])")
_HANDLE_HINT_RE = re.compile(
    r"\b(?:username|handle|user)\s*(?::|=|\bis\b|\bnamed\b|\bcalled\b)?\s*[\"']?@?([A-Za-z0-9][A-Za-z0-9_.-]{1,63})",
    re.IGNORECASE,
)
_HANDLE_AFTER_RE = re.compile(
    r"\b(?:alias|behind|called|named)\s+[\"']?@?([A-Za-z0-9][A-Za-z0-9_.-]{1,63})",
    re.IGNORECASE,
)
_PERSON_NAME_RE = re.compile(
    r"\b(?:person|individual|name|person_name)\s*(?::|=|\bis\b|\bnamed\b|\bcalled\b)\s*[\"']?([^\"']+?)[\"']?(?:[?.!,]|$)",
    re.IGNORECASE,
)
_EXPLICIT_PREFIX_RE = re.compile(
    r"^(username|handle|email|phone|domain|url|ip|name|person_name|company|company_name|hashtag)\s*[:=]\s*(.+)$",
    re.IGNORECASE,
)
_VALID_HANDLE_RE = re.compile(r"^@?[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$")


def _clean_query_value(value: str) -> str:
    return value.strip().strip("\"'").rstrip(".,;:!?)]}").lstrip("@")


def _query_handle(value: str) -> Seed | None:
    cleaned = _clean_query_value(value)
    if not cleaned or cleaned.casefold() in _QUERY_STOPWORDS:
        return None
    if not _VALID_HANDLE_RE.fullmatch(cleaned):
        return None
    return Seed(type=SeedType.USERNAME, value=cleaned)


def parse_ask_query(query: str) -> Seed:
    """Parse a natural-language question into one legal, typed seed.

    This is intentionally a deterministic regex parser: it never calls a
    remote service before the operator has authorized the investigation. An
    operator can always bypass it with an explicit ``type:value`` seed.
    """
    text = " ".join(query.split()).strip()
    if not text:
        raise SystemExit("ask query is empty")

    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE):
        explicit = _EXPLICIT_PREFIX_RE.match(text)
        if explicit:
            raw_kind = explicit.group(1).casefold()
            kind = _QUERY_SEED_TYPES.get(raw_kind, SeedType(raw_kind))
            value = _clean_query_value(explicit.group(2))
            if not value:
                raise SystemExit("ask query has an empty seed value")
            return Seed(type=kind, value=value)

    email = _EMAIL_RE.search(text)
    if email:
        return Seed(type=SeedType.EMAIL, value=email.group(0))

    url = _URL_RE.search(text)
    if url:
        return Seed(type=SeedType.URL, value=_clean_query_value(url.group(0)))

    for candidate in _IP_RE.findall(text):
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return Seed(type=SeedType.IP, value=candidate)

    for handle in _HANDLE_HINT_RE.finditer(text):
        seed = _query_handle(handle.group(1))
        if seed is not None:
            return seed

    at_handle = re.search(r"(?<![\w.])@([A-Za-z0-9][A-Za-z0-9_.-]{1,63})\b", text)
    if at_handle:
        seed = _query_handle(at_handle.group(1))
        if seed is not None:
            return seed

    domain_hint = re.search(
        r"\bdomain\s*(?::|=|\bis\b|\bnamed\b|\bcalled\b)?\s*[\"']?([A-Za-z0-9.-]+\.[A-Za-z]{2,63})",
        text,
        re.IGNORECASE,
    )
    if domain_hint:
        return Seed(type=SeedType.DOMAIN, value=_clean_query_value(domain_hint.group(1)))

    hashtag = re.search(r"(?<!\w)#([A-Za-z0-9_]{2,100})\b", text)
    if hashtag:
        return Seed(type=SeedType.HASHTAG, value=f"#{hashtag.group(1)}")

    phone = _PHONE_RE.search(text)
    if phone:
        value = re.sub(r"[\s().-]+", "", phone.group(1))
        if len(re.sub(r"\D", "", value)) >= 7:
            return Seed(type=SeedType.PHONE, value=value)

    person = _PERSON_NAME_RE.search(text)
    if person:
        value = _clean_query_value(person.group(1))
        if len(value) >= 2 and value.casefold() not in _QUERY_STOPWORDS:
            return Seed(type=SeedType.PERSON_NAME, value=value)

    after = _HANDLE_AFTER_RE.search(text)
    if after:
        seed = _query_handle(after.group(1))
        if seed is not None:
            return seed

    domain = _DOMAIN_RE.search(text)
    if domain:
        return Seed(type=SeedType.DOMAIN, value=domain.group(0).rstrip("."))

    bare = _query_handle(text)
    if bare is not None:
        return bare

    raise SystemExit(
        "Could not parse a seed from the query. Use an explicit seed such as "
        "username:alice, email:alice@example.com, domain:example.com, or url:https://example.com/profile"
    )


def _ask_cascade_config(args: argparse.Namespace, seed: Seed):
    from aletheia.cascade.runner import CascadeRunConfig

    return CascadeRunConfig(
        data_root=Path(args.data_dir),
        seeds=[seed],
        authorization_assertion=args.authorization_assertion,
        case_id=args.case_id,
        timeout_seconds=args.timeout,
        proxy_url=args.proxy,
        wire_egress=not args.no_egress_proxy,
        egress_rate=args.egress_rate,
        egress_burst=args.egress_burst,
        max_expansions=args.max_expansions,
        owner_mode=args.owner_mode,
    )


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
                    proxy_url=args.proxy, wire_egress=not args.no_egress_proxy,
                    egress_rate=args.egress_rate, egress_burst=args.egress_burst)
        print(f"completed: {run_id}")
    elif args.cmd == "ask":
        from aletheia.cascade.runner import fixture_observer, run_cascade
        from aletheia.reporting.dossier import generate_dossier

        seed = parse_ask_query(args.query)
        print(f"seed={seed.type.value}:{seed.value}")
        observer = fixture_observer(Path(args.fixture)) if args.fixture else None
        outcome = run_cascade(_ask_cascade_config(args, seed), observer=observer)
        print(f"run: {outcome.run_id}")
        for name, path in outcome.artifacts.items():
            print(f"{name}={path}")
        print(f"stop_reason={outcome.stop_reason}")
        print(f"expansions={outcome.expansions}")
        print(f"coverage_ok={outcome.coverage_ok}")
        generate_dossier(
            str(outcome.run_id),
            args.data_dir,
            args.llm_url,
            model=args.llm_model,
        )
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
                    wire_egress=not args.no_egress_proxy,
                    egress_rate=args.egress_rate, egress_burst=args.egress_burst)
        print(f"resumed: {args.run_id}")
    elif args.cmd == "cascade":
        from aletheia.core.case_store import CaseStore
        from aletheia.core.labels import ConfirmLabel, LabelStore

        if args.cascade_cmd == "run":
            from aletheia.cascade.runner import CascadeRunConfig, fixture_observer, run_cascade

            config = CascadeRunConfig(
                data_root=Path(args.data_dir),
                seeds=[parse_seed(raw) for raw in args.seed],
                authorization_assertion=args.authorization_assertion,
                case_id=args.case_id,
                timeout_seconds=args.timeout,
                proxy_url=args.proxy,
                wire_egress=not args.no_egress_proxy,
                egress_rate=args.egress_rate,
                egress_burst=args.egress_burst,
                max_expansions=args.max_expansions,
                owner_mode=args.owner_mode,
                interactive=getattr(args, "interactive", False),
                calibration_pairs_path=(
                    Path(args.calibration_pairs)
                    if getattr(args, "calibration_pairs", None)
                    else None
                ),
            )
            observer = fixture_observer(Path(args.fixture)) if args.fixture else None
            outcome = run_cascade(config, observer=observer)
            print(f"run: {outcome.run_id}")
            for name, path in outcome.artifacts.items():
                print(f"{name}={path}")
            print(f"stop_reason={outcome.stop_reason}")
            print(f"expansions={outcome.expansions}")
            print(f"trail_digest={outcome.trail_digest}")
            print(f"coverage_ok={outcome.coverage_ok}")
            if getattr(args, "interactive", False):
                print(f"labels_recorded={outcome.labels_recorded}")
        elif args.cascade_cmd == "review":
            from aletheia.cascade.ledger import DecisionLedger

            raw = Path(args.ledger).read_text(encoding="utf-8")
            records = (
                json.loads(raw)
                if raw.lstrip().startswith("[")
                else [json.loads(line) for line in raw.splitlines() if line.strip()]
            )
            try:
                ledger = DecisionLedger.from_dicts(records)
            except ValueError as exc:
                print(f"invalid ledger: {exc}")
                raise SystemExit(1)
            ok, detail = ledger.verify()
            print(f"ledger: {detail}")
            kinds = [kind for kind in (args.kinds or "").split(",") if kind] or None
            for entry in ledger.replay(kinds=kinds):
                print(f"{entry.sequence:>4}  {entry.kind}  {json.dumps(dict(entry.payload), sort_keys=True)}")
        elif args.cascade_cmd == "confirm":
            store = LabelStore(Path(args.data_dir) / "labels.jsonl")
            record = store.add(
                case_id=args.case_id,
                cluster_id=args.cluster_id,
                label=ConfirmLabel(args.label),
                score=args.score,
                note=args.note,
            )
            print(f"recorded: {record.case_id}/{record.cluster_id} = {record.label.value}")
        else:
            data_dir = Path(args.data_dir)
            case_store = CaseStore(data_dir / "cases")
            inventory = case_store.purge(args.case_id)
            removed = LabelStore(data_dir / "labels.jsonl").purge_case(str(args.case_id))
            print(
                "case file: deleted "
                f"({inventory['runs_removed']} runs, {inventory['snapshots_removed']} snapshots, "
                f"{inventory['timeline_events']} timeline events)"
            )
            print(f"labels removed: {removed}")
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
