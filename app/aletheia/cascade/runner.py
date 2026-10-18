"""Cascade run wiring: fixture dry-runs and live adapter-backed runs (P17.10).

Design of record: ``docs/PIVOT_CASCADE.md`` sections 12-14. One cascade run is
one audited run:

- the run manifest carries the authorization assertion (verbatim) and the
  scheduler checkpoint under ``manifest["cascade"]`` (frontier, budget,
  stop reason — section 14);
- every adapter invocation is recorded on the run's ``AUDIT.jsonl`` chain,
  and network egress goes through the same per-adapter proxy wired for
  ``resume`` (an adapter whose descriptor declares ``network_required=True``
  runs with the proxy as its only way out);
- artifacts are written under ``runs/<run_id>/cascade/``: ``ledger.jsonl``
  (the hash-chained decision ledger), ``trail.json`` (parent-linked hops with
  the golden digest), ``dossier.json`` (tiered fields with evidence chains),
  ``coverage.json`` (the end-of-run audit; any violation raises), and
  ``next_actions.json``;
- when a case id is given, the run and its summary are recorded on the case
  (P17.7 case memory), never silently.

Two observers exist:

- :func:`fixture_observer` reads a JSON fixture (``{"answers": {"TYPE:value":
  {"findings": [...], "blocked_reason": "..."}}}``) and performs no I/O at
  all — the CI dry-run path;
- :class:`AdapterObserver` runs the real adapters — the only live path. It
  never retries: one invocation per (adapter, granted pivot), failures
  collapse into a recorded ``blocked_reason``.

Skip records (missing keys, retired endpoints) are source metadata, not
observations: they stay on the manifest and the coverage audit, and are
filtered out of the findings the engine sees.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from aletheia.cascade.claims import claim_from_finding
from aletheia.cascade.coverage import assert_coverage, build_coverage
from aletheia.cascade.dossier import (
    DossierCluster,
    DossierField,
    EvidenceRef,
    build_dossier,
)
from aletheia.cascade.engine import CascadeEngine, Observation, Observer
from aletheia.cascade.ledger import DecisionLedger
from aletheia.cascade.next_actions import build_next_actions
from aletheia.cascade.scheduler import SchedulerPolicy
from aletheia.cascade.trail import build_trail, trail_digest
from aletheia.core import egress
from aletheia.core.audit import AuditLogger
from aletheia.core.case_store import CaseStore
from aletheia.core.chain import tip as audit_chain_tip
from aletheia.core.models import (
    AdapterRunRequest,
    AuditEvent,
    ClusterDecision,
    Finding,
    IdentityTier,
    Seed,
    SeedType,
)
from aletheia.core.orchestrator import Orchestrator, extract_skipped_sources

__all__ = [
    "AdapterObserver",
    "CascadeRunConfig",
    "CascadeRunOutcome",
    "fixture_observer",
    "run_cascade",
]

_TIERED = (IdentityTier.PROBABLE, IdentityTier.POSSIBLE)


@dataclass(frozen=True)
class CascadeRunConfig:
    """Everything one cascade run needs; mirrors the investigate CLI knobs."""

    data_root: Path
    seeds: Sequence[Seed]
    authorization_assertion: str | None = None
    case_id: UUID | None = None
    timeout_seconds: int = 120
    proxy_url: str | None = None
    wire_egress: bool = True
    egress_rate: float = 1.0
    egress_burst: float = 1.0
    max_expansions: int | None = None
    owner_mode: bool = False
    subject_label: str = "subject"


@dataclass(frozen=True)
class CascadeRunOutcome:
    """Where the run landed and the numbers to copy into evidence logs."""

    run_id: UUID
    artifacts: Mapping[str, str]
    stop_reason: str
    expansions: int
    passes: int
    trail_digest: str
    coverage_ok: bool


def _is_skip_finding(finding: Finding) -> bool:
    """Mirror of ``orchestrator.extract_skipped_sources``'s detection rules."""
    attributes = finding.attributes or {}
    details = attributes.get("details") if isinstance(attributes.get("details"), dict) else {}
    raw = attributes.get("raw_evidence") if isinstance(attributes.get("raw_evidence"), dict) else {}
    return (
        attributes.get("skipped") is True
        or details.get("skipped") is True
        or raw.get("skipped") is True
        or str(finding.value).endswith(":skipped")
    )


def fixture_observer(path: Path) -> Observer:
    """Build a pure fixture observer from a JSON file (no I/O at call time).

    Keys are the canonical ``TYPE:value`` the engine will request
    (``canonicalize_seed`` output); unknown seeds answer empty, exactly like
    an adapter that returned nothing.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    answers: dict[tuple[SeedType, str], Observation] = {}
    for key, payload in raw.get("answers", {}).items():
        seed_type, _, seed_value = str(key).partition(":")
        findings = tuple(Finding.model_validate(item) for item in payload.get("findings", []))
        answers[(SeedType(seed_type), seed_value)] = Observation(
            findings=findings, blocked_reason=str(payload.get("blocked_reason", ""))
        )

    def observe(seed: Seed) -> Observation:
        return answers.get((seed.type, seed.value), Observation())

    return observe


def _safe_label(sequence: int, adapter_name: str, seed: Seed) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", seed.value)[:40] or "seed"
    return f"{sequence:04d}_{adapter_name}_{safe}"


class AdapterObserver:
    """The live observer: one adapter invocation per supporting adapter.

    ``wire_egress`` mirrors the orchestrator: a network-required adapter runs
    with the egress proxy as its only way out; the proxy log is appended to
    the audit chain and counted into the coverage audit's egress totals
    (``refused`` = the proxy answered 429). Nothing is retried here — an
    expansion happens once, and every failure is recorded.
    """

    def __init__(
        self,
        *,
        adapters: Mapping[str, Any],
        run_id: UUID,
        audit: AuditLogger,
        workspace_root: Path,
        data_root: Path,
        authorization_assertion: str | None,
        timeout_seconds: int = 120,
        proxy_url: str | None = None,
        wire_egress: bool = True,
        egress_rate: float = 1.0,
        egress_burst: float = 1.0,
    ) -> None:
        self._adapters = adapters
        self._run_id = run_id
        self._audit = audit
        self._workspace_root = Path(workspace_root)
        self._data_root = Path(data_root)
        self._authorization_assertion = authorization_assertion
        self._timeout_seconds = int(timeout_seconds)
        self._proxy_url = proxy_url
        self._wire_egress = bool(wire_egress)
        self._egress_rate = float(egress_rate)
        self._egress_burst = float(egress_burst)
        self.invocations = 0
        self.ran: set[str] = set()
        self.skips: dict[str, str] = {}
        self.blocked: dict[str, str] = {}
        self.egress_totals: dict[str, int] = {"total": 0, "allowed": 0, "refused": 0}
        # One egress session per adapter for the whole run: the Docker network
        # name is derived from the adapter name, so a second session for the
        # same adapter would collide, and a re-run of an adapter must never
        # quietly run unwired. Proxy entries are chained incrementally per
        # drain so nothing is duplicated across invocations.
        self._sessions: dict[str, egress.ProxySession] = {}
        self._appended: dict[str, int] = {}
        self._session_failed: dict[str, str] = {}

    def __call__(self, seed: Seed) -> Observation:
        supporting = sorted(
            (name, adapter)
            for name, adapter in self._adapters.items()
            if adapter.supports(seed.type)
        )
        findings: list[Finding] = []
        errors: list[str] = []
        for name, adapter in supporting:
            self.invocations += 1
            workspace = self._workspace_root / _safe_label(self.invocations, name, seed)
            session = None
            proxy_url = self._proxy_url
            network = None
            if self._wire_egress and egress.is_wired(
                name, network_required=adapter.descriptor.network_required
            ):
                session = self._sessions.get(name)
                if session is None and name in self._session_failed:
                    # A failed wiring attempt never becomes an unwired run: the
                    # adapter stays blocked for the rest of this run.
                    reason = f"egress wiring failed earlier in this run: {self._session_failed[name]}"
                    errors.append(f"{name}: {reason}")
                    self.blocked.setdefault(name, self._session_failed[name])
                    continue
                if session is None:
                    candidate = egress.ProxySession(
                        name,
                        self._workspace_root / "egress" / name,
                        rate=self._egress_rate,
                        capacity=self._egress_burst,
                    )
                    try:
                        candidate.start()
                    except Exception as exc:  # noqa: BLE001 - recorded, never silent
                        self._session_failed[name] = str(exc)[:300]
                        self.blocked[name] = str(exc)[:300]
                        errors.append(f"{name}: egress wiring failed: {exc}")
                        self._audit.log(
                            AuditEvent(
                                run_id=self._run_id,
                                event_type="cascade_adapter_error",
                                adapter=name,
                                request_meta={
                                    "seed_type": seed.type.value,
                                    "seed_value": seed.value,
                                    "error": f"egress session start failed: {exc}"[:500],
                                },
                                outcome="error",
                            )
                        )
                        candidate.stop()
                        continue
                    self._sessions[name] = candidate
                    session = candidate
                proxy_url = session.proxy_url
                network = session.network
            try:
                request = AdapterRunRequest(
                    run_id=self._run_id,
                    seed=seed,
                    legal_only=True,
                    authorization_assertion=self._authorization_assertion,
                    timeout_seconds=self._timeout_seconds,
                    proxy_url=proxy_url,
                    network_name=network,
                    seed_index=0,
                )
                result = adapter.run(request, workspace, self._audit)
            except Exception as exc:  # noqa: BLE001 - recorded, never silent
                errors.append(f"{name}: {exc}")
                self.blocked[name] = str(exc)[:300]
                self._audit.log(
                    AuditEvent(
                        run_id=self._run_id,
                        event_type="cascade_adapter_error",
                        adapter=name,
                        request_meta={
                            "seed_type": seed.type.value,
                            "seed_value": seed.value,
                            "error": str(exc)[:500],
                        },
                        outcome="error",
                    )
                )
                continue
            finally:
                if session is not None:
                    # Sessions persist across invocations of the same adapter;
                    # only the not-yet-chained proxy entries are appended.
                    self._drain_egress(name, session)
            findings.extend(result.findings)
            self.ran.add(name)
            for skip in extract_skipped_sources(result.findings):
                self.skips.setdefault(skip["source"], skip["reason"])
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "result.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
        kept = tuple(finding for finding in findings if not _is_skip_finding(finding))
        if kept:
            return Observation(findings=kept)
        if errors:
            return Observation(blocked_reason="; ".join(errors)[:500])
        return Observation()

    def _drain_egress(self, name: str, session: egress.ProxySession) -> None:
        """Chain the proxy entries produced since the last drain for ``name``."""
        entries = session.read_entries()
        already = self._appended.get(name, 0)
        self._appended[name] = len(entries)
        fresh = entries[already:]
        if not fresh:
            return
        egress.append_log_to_chain(self._run_id, fresh, data_root=self._data_root)
        for entry in fresh:
            self.egress_totals["total"] += 1
            if entry.status == 429:
                self.egress_totals["refused"] += 1
            else:
                self.egress_totals["allowed"] += 1

    def close(self) -> None:
        """Drain every reused session and tear its wiring down (never raises)."""
        for name, session in list(self._sessions.items()):
            try:
                self._drain_egress(name, session)
            finally:
                session.stop()
        self._sessions.clear()


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return str(path)


def _clusters(
    result: Any, root_claims: Sequence[Any]
) -> list[DossierCluster]:
    decision_by_claim: dict[UUID, ClusterDecision] = {
        decision.entity_ids[1]: decision for decision in result.decisions
    }
    anchor_ids = {claim.claim_id for claim in root_claims}
    fields: list[DossierField] = []
    for claim in result.subject_claims:
        if claim.claim_id in anchor_ids:
            reference = EvidenceRef(
                kind="anchor",
                source=f"{claim.type.value}:{claim.value}",
                note="investigation anchor claim",
            )
        else:
            decision = decision_by_claim.get(claim.claim_id)
            reference = EvidenceRef(
                kind="merge",
                source=str(decision.decision_id) if decision is not None else "",
                note=decision.reason if decision is not None else "",
            )
        fields.append(DossierField(entity_type=claim.type, value=claim.value, evidence=(reference,)))
    clusters = [
        DossierCluster(cluster_id="subject", tier=IdentityTier.CONFIRMED, fields=tuple(fields))
    ]
    for case in result.candidates:
        if case.accepted or case.tier is None:
            continue
        decision = decision_by_claim.get(case.claim.claim_id)
        reference = EvidenceRef(
            kind="veto" if case.veto else "decision",
            source=str(decision.decision_id) if decision is not None else "",
            note=case.reason,
        )
        clusters.append(
            DossierCluster(
                cluster_id=str(case.claim.claim_id),
                tier=case.tier,
                fields=(
                    DossierField(
                        entity_type=case.claim.type, value=case.claim.value, evidence=(reference,)
                    ),
                ),
            )
        )
    return clusters


def run_cascade(config: CascadeRunConfig, *, observer: Observer | None = None) -> CascadeRunOutcome:
    """Run one cascade (live when ``observer`` is None) and write its artifacts."""
    orchestrator = Orchestrator(config.data_root)
    run_id = orchestrator.create_run(
        list(config.seeds), legal_only=True, authorization_assertion=config.authorization_assertion
    )
    run_dir = orchestrator.checkpoints.run_dir(run_id)
    cascade_dir = run_dir / "cascade"
    cascade_dir.mkdir(parents=True, exist_ok=True)
    audit = AuditLogger(run_dir / "AUDIT.jsonl")
    audit.log(
        AuditEvent(
            run_id=run_id,
            event_type="cascade_run_started",
            request_meta={
                "mode": "fixture" if observer is not None else "live",
                "seeds": [f"{seed.type.value}:{seed.value}" for seed in config.seeds],
                "authorized": bool(config.authorization_assertion),
            },
            outcome="started",
        )
    )

    live: AdapterObserver | None = None
    expected_adapters: list[str] = []
    if observer is None:
        expected_adapters = sorted(
            name
            for name, adapter in orchestrator.adapters.items()
            if any(adapter.supports(seed.type) for seed in config.seeds)
        )
        live = AdapterObserver(
            adapters=orchestrator.adapters,
            run_id=run_id,
            audit=audit,
            workspace_root=cascade_dir / "expansions",
            data_root=config.data_root,
            authorization_assertion=config.authorization_assertion,
            timeout_seconds=config.timeout_seconds,
            proxy_url=config.proxy_url,
            wire_egress=config.wire_egress,
            egress_rate=config.egress_rate,
            egress_burst=config.egress_burst,
        )
        observer = live

    root_findings: list[Finding] = []
    for seed in config.seeds:
        observation = observer(seed)
        if observation.blocked_reason:
            audit.log(
                AuditEvent(
                    run_id=run_id,
                    event_type="cascade_root_blocked",
                    request_meta={
                        "seed_type": seed.type.value,
                        "seed_value": seed.value,
                        "reason": observation.blocked_reason,
                    },
                    outcome="blocked",
                )
            )
        root_findings.extend(observation.findings)
    root_claims = [claim_from_finding(finding) for finding in root_findings]
    if not root_claims:
        audit.log(
            AuditEvent(
                run_id=run_id,
                event_type="cascade_run_failed",
                request_meta={"reason": "no root claims were observed"},
                outcome="failed",
            )
        )
        manifest = orchestrator.checkpoints.load(run_id) or {}
        manifest["cascade"] = {
            "mode": "fixture" if live is None else "live",
            "authorization_assertion": config.authorization_assertion,
            "stop_reason": "no_root_claims",
            "expansions": 0,
            "passes": 0,
        }
        manifest["chain_tip"] = audit_chain_tip(run_id, data_root=config.data_root)
        orchestrator.checkpoints.save(run_id, manifest)
        raise RuntimeError("cascade run has no root claims (every root adapter returned nothing or was blocked)")

    ledger = DecisionLedger()
    engine = CascadeEngine(
        observer,
        policy=SchedulerPolicy(owner_mode=config.owner_mode, max_expansions=config.max_expansions),
        ledger=ledger,
    )
    try:
        result = engine.run(root_claims, subject_label=config.subject_label)
    finally:
        if live is not None:
            live.close()

    ledger_path = cascade_dir / "ledger.jsonl"
    ledger_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in ledger.to_dicts()) + "\n",
        encoding="utf-8",
    )
    trail_path = _write_json(
        cascade_dir / "trail.json",
        build_trail(
            result.hops,
            run_id=str(run_id),
            case_id=str(config.case_id) if config.case_id is not None else None,
        ),
    )
    dossier_path = _write_json(
        cascade_dir / "dossier.json",
        build_dossier(
            subject_seeds=list(config.seeds),
            clusters=_clusters(result, root_claims),
            run_id=str(run_id),
            case_id=str(config.case_id) if config.case_id is not None else None,
        ),
    )

    proposals: dict[SeedType, int] = {}
    gated: dict[SeedType, int] = {}
    for entry in ledger.replay(kinds=["pivot_proposed", "pivot_gated"]):
        seed_type = SeedType(entry.payload["seed_type"])
        if entry.kind == "pivot_proposed":
            proposals[seed_type] = proposals.get(seed_type, 0) + 1
        else:
            gated[seed_type] = gated.get(seed_type, 0) + 1
    gate_evaluations = {
        seed_type: gated.get(seed_type, 0) + proposals.get(seed_type, 0)
        for seed_type in set(proposals) | set(gated)
    }
    skips: dict[str, str] = {}
    if live is not None:
        skips.update(live.skips)
        for name, reason in live.blocked.items():
            skips.setdefault(name, f"blocked: {reason}")
    egress_payload = (
        dict(live.egress_totals)
        if live is not None and config.wire_egress
        else None
    )
    coverage = build_coverage(
        expected_adapters=expected_adapters,
        ran_adapters=sorted(live.ran) if live is not None else [],
        skips=skips,
        pivot_proposals=proposals,
        gate_evaluations=gate_evaluations,
        egress=egress_payload,
        run_id=str(run_id),
    )
    coverage_path = _write_json(cascade_dir / "coverage.json", coverage.payload)
    assert_coverage(coverage)

    next_actions_path = _write_json(
        cascade_dir / "next_actions.json",
        build_next_actions(
            clusters_to_confirm=[
                str(case.claim.claim_id)
                for case in result.candidates
                if case.tier in _TIERED
            ],
            blocked_sources=skips,
        ),
    )

    manifest = orchestrator.checkpoints.load(run_id) or {}
    digest = trail_digest(build_trail(result.hops))
    audit.log(
        AuditEvent(
            run_id=run_id,
            event_type="cascade_run_finished",
            request_meta={
                "stop_reason": result.stop_reason.value,
                "expansions": result.expansions,
                "passes": result.passes,
                "trail_digest": digest,
                "coverage_ok": coverage.ok,
            },
            outcome="completed",
        )
    )
    manifest["cascade"] = {
        "mode": "fixture" if live is None else "live",
        "authorization_assertion": config.authorization_assertion,
        "stop_reason": result.stop_reason.value,
        "stop_note": result.stop_note,
        "expansions": result.expansions,
        "passes": result.passes,
        "root_claims": len(root_claims),
        "subject_claims": len(result.subject_claims),
        "trail_digest": digest,
        "coverage_ok": coverage.ok,
        "scheduler_checkpoint": result.checkpoint,
        "artifacts": {
            "ledger": str(ledger_path),
            "trail": trail_path,
            "dossier": dossier_path,
            "coverage": coverage_path,
            "next_actions": next_actions_path,
        },
    }
    manifest["chain_tip"] = audit_chain_tip(run_id, data_root=config.data_root)
    orchestrator.checkpoints.save(run_id, manifest)

    if config.case_id is not None:
        cases = CaseStore(config.data_root / "cases")
        cases.record_run(
            config.case_id,
            run_id=run_id,
            summary={
                "mode": manifest["cascade"]["mode"],
                "stop_reason": result.stop_reason.value,
                "expansions": result.expansions,
            },
        )
        cases.snapshot(
            config.case_id,
            {
                "cascade": {
                    "trail_digest": digest,
                    "stop_reason": result.stop_reason.value,
                    "expansions": result.expansions,
                    "passes": result.passes,
                }
            },
        )

    return CascadeRunOutcome(
        run_id=run_id,
        artifacts={
            "ledger": str(ledger_path),
            "trail": trail_path,
            "dossier": dossier_path,
            "coverage": coverage_path,
            "next_actions": next_actions_path,
        },
        stop_reason=result.stop_reason.value,
        expansions=result.expansions,
        passes=result.passes,
        trail_digest=digest,
        coverage_ok=coverage.ok,
    )
