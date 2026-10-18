"""Tests for the cascade runner wiring (P17.10).

The fixture dry-run path performs no I/O at all and covers the full pipeline:
manifest + audit chain + ledger + trail + dossier + coverage + next actions.
The live observer is exercised with stub adapters only — no network, no
Docker, no skips.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from pydantic import BaseModel, Field

from aletheia.cascade.engine import Observation
from aletheia.cascade.runner import (
    AdapterObserver,
    CascadeRunConfig,
    fixture_observer,
    run_cascade,
)
from aletheia.cli.main import main
from aletheia.core import chain
from aletheia.core.audit import AuditLogger
from aletheia.core.models import EntityType, Finding, Provenance, Seed, SeedType
from aletheia.core.orchestrator import Orchestrator


def _finding(entity_type: EntityType, value: str, tool: str = "world") -> Finding:
    return Finding(
        entity_type=entity_type,
        value=value,
        provenance=Provenance(tool=tool, confidence=1.0, adapter_version="fixture-1"),
    )


def _fixture_file(tmp_path: Path, answers: dict[str, dict[str, object]]) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"answers": answers}), encoding="utf-8")
    return path


def _echo_answers() -> dict[str, dict[str, object]]:
    return {
        "email:alice@example.com": {
            "findings": [
                {
                    "entity_type": "email",
                    "value": "alice@example.com",
                    "provenance": {
                        "tool": "world-mail",
                        "confidence": 1.0,
                        "adapter_version": "fixture-1",
                    },
                }
            ]
        }
    }


class _StubResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


class _StubAdapter:
    def __init__(
        self,
        seed_types: set[SeedType],
        findings: list[Finding] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._seed_types = seed_types
        self._findings = list(findings or [])
        self._error = error
        self.calls = 0
        self.descriptor = SimpleNamespace(network_required=False)

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in self._seed_types

    def run(self, request, workspace: Path, audit: AuditLogger) -> _StubResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        workspace.mkdir(parents=True, exist_ok=True)
        return _StubResult(findings=self._findings)


def _config(data_root: Path, value: str = "alice@example.com") -> CascadeRunConfig:
    return CascadeRunConfig(
        data_root=data_root, seeds=[Seed(type=SeedType.EMAIL, value=value)]
    )


def test_fixture_dry_run_writes_verified_artifacts(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    outcome = run_cascade(
        _config(data_root), observer=fixture_observer(_fixture_file(tmp_path, _echo_answers()))
    )

    assert outcome.stop_reason == "saturated"
    assert outcome.coverage_ok is True
    for key in ("ledger", "trail", "dossier", "coverage", "next_actions"):
        path = Path(outcome.artifacts[key])
        assert path.exists(), key
        text = path.read_text(encoding="utf-8")
        assert text.strip(), key
        if path.suffix == ".json":
            assert isinstance(json.loads(text), dict)

    manifest = Orchestrator(data_root).checkpoints.load(outcome.run_id)
    cascade = manifest["cascade"]
    assert cascade["mode"] == "fixture"
    assert cascade["stop_reason"] == "saturated"
    assert cascade["expansions"] >= 1
    assert cascade["subject_claims"] >= 1
    assert isinstance(cascade["scheduler_checkpoint"], dict)
    assert manifest["chain_tip"]

    trail = json.loads(Path(outcome.artifacts["trail"]).read_text(encoding="utf-8"))
    assert trail["hops"][0]["outcome"] == "expanded"

    verification = chain.verify(outcome.run_id, data_root=data_root)
    assert verification["valid"] is True
    assert verification["anchored"] is True


def test_fixture_runs_are_deterministic_across_data_roots(tmp_path: Path) -> None:
    first = run_cascade(
        _config(tmp_path / "d1"), observer=fixture_observer(_fixture_file(tmp_path, _echo_answers()))
    )
    second = run_cascade(
        _config(tmp_path / "d2"), observer=fixture_observer(_fixture_file(tmp_path, _echo_answers()))
    )
    assert first.trail_digest == second.trail_digest
    assert first.stop_reason == second.stop_reason


def test_blocked_pivot_lands_in_the_trail(tmp_path: Path) -> None:
    answers = _echo_answers()
    answers["domain:example.com"] = {"blocked_reason": "HTTP 429 from world-dns (rate limited)"}
    outcome = run_cascade(
        _config(tmp_path / "data"), observer=fixture_observer(_fixture_file(tmp_path, answers))
    )

    trail = json.loads(Path(outcome.artifacts["trail"]).read_text(encoding="utf-8"))
    blocked = [hop for hop in trail["hops"] if hop["outcome"] == "blocked"]
    assert len(blocked) == 1
    assert "429" in blocked[0]["reason"]
    assert outcome.stop_reason == "saturated"


def test_run_fails_loudly_without_any_root_claim(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    fixture = _fixture_file(
        tmp_path,
        {"email:alice@example.com": {"blocked_reason": "HTTP 429 from world-mail"}},
    )
    with pytest.raises(RuntimeError, match="no root claims"):
        run_cascade(_config(data_root), observer=fixture_observer(fixture))

    audit_text = next(data_root.rglob("AUDIT.jsonl")).read_text(encoding="utf-8")
    assert "cascade_run_failed" in audit_text


def test_adapter_observer_runs_supporting_adapters_once(tmp_path: Path) -> None:
    finding = _finding(EntityType.HOST, "example.com", "stub")
    skip = Finding(
        entity_type=EntityType.URL,
        value="code_search:skipped",
        attributes={"skip_reason": "missing token"},
        provenance=Provenance(tool="stub", confidence=1.0, adapter_version="conf-1"),
    )
    good = _StubAdapter({SeedType.DOMAIN}, findings=[finding, skip])
    audit = AuditLogger(tmp_path / "AUDIT.jsonl")
    observer = AdapterObserver(
        adapters={"good": good},
        run_id=uuid5(NAMESPACE_URL, "aletheia:test:observer"),
        audit=audit,
        workspace_root=tmp_path / "ws",
        data_root=tmp_path,
        authorization_assertion="authorized by the owner",
        timeout_seconds=5,
        wire_egress=False,
    )

    seed = Seed(type=SeedType.DOMAIN, value="example.com")
    observation = observer(seed)
    # The skip record is source metadata: it stays out of the engine's claims
    # and lands in the observer's skip map instead.
    assert [f.value for f in observation.findings] == ["example.com"]
    assert observation.blocked_reason == ""
    assert observer.skips == {"code_search": "missing token"}
    assert good.calls == 1
    assert observer.ran == {"good"}
    assert observer.invocations == 1
    assert list((tmp_path / "ws").rglob("result.json"))

    # Unsupported seed types invoke nothing, and nothing is ever retried.
    assert observer(Seed(type=SeedType.IP, value="203.0.113.7")) == Observation()
    assert good.calls == 1


def test_adapter_observer_records_failures_as_blocked(tmp_path: Path) -> None:
    bad = _StubAdapter({SeedType.DOMAIN}, error=RuntimeError("boom"))
    observer = AdapterObserver(
        adapters={"bad": bad},
        run_id=uuid4(),
        audit=AuditLogger(tmp_path / "AUDIT.jsonl"),
        workspace_root=tmp_path / "ws",
        data_root=tmp_path,
        authorization_assertion=None,
        wire_egress=False,
    )
    observation = observer(Seed(type=SeedType.DOMAIN, value="example.com"))

    assert observation.findings == ()
    assert "boom" in observation.blocked_reason
    assert observer.blocked == {"bad": "boom"}
    assert observer.ran == set()
    audit_text = (tmp_path / "AUDIT.jsonl").read_text(encoding="utf-8")
    assert "cascade_adapter_error" in audit_text


def test_cli_cascade_run_fixture_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    fixture = _fixture_file(tmp_path, _echo_answers())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aletheia",
            "cascade",
            "run",
            "--seed",
            "email:alice@example.com",
            "--fixture",
            str(fixture),
            "--data-dir",
            str(tmp_path / "cli-data"),
        ],
    )
    main()
    out = capsys.readouterr().out
    assert "stop_reason=saturated" in out
    assert "coverage_ok=True" in out
    assert "trail_digest=" in out
    assert "expansions=" in out


# -- live observer without Docker (stubbed egress sessions) --------------------


class _FakeSession:
    """Records session lifecycle; entries are fed in by the test."""

    def __init__(self, adapter: str, log_dir: Path, rate: float = 1.0, capacity: float = 1.0) -> None:
        self.adapter = adapter
        self.log_dir = Path(log_dir)
        self.proxy_url = f"http://proxy.invalid:8899/{adapter}"
        self.network = f"aletheia-egress-net-{adapter}"
        self.entries: list[SimpleNamespace] = []
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def read_entries(self) -> list[SimpleNamespace]:
        return list(self.entries)

    def stop(self) -> None:
        self.stopped += 1


def _patch_egress(monkeypatch, factory):
    from aletheia.core import egress as egress_module

    chained: list[list[SimpleNamespace]] = []
    monkeypatch.setattr(egress_module, "ProxySession", factory)
    monkeypatch.setattr(egress_module, "is_wired", lambda name, network_required=False: True)
    monkeypatch.setattr(
        egress_module,
        "append_log_to_chain",
        lambda run_id, entries, data_root=None: chained.append(list(entries)),
    )
    return chained


def test_adapter_observer_reuses_one_egress_session_per_adapter(tmp_path, monkeypatch) -> None:
    sessions: list[_FakeSession] = []

    def factory(adapter, log_dir, rate=1.0, capacity=1.0):
        session = _FakeSession(adapter, log_dir, rate, capacity)
        sessions.append(session)
        return session

    chained = _patch_egress(monkeypatch, factory)

    good = _StubAdapter(
        {SeedType.DOMAIN}, findings=[_finding(EntityType.HOST, "example.com", "stub")]
    )
    good.descriptor = SimpleNamespace(network_required=True)
    observer = AdapterObserver(
        adapters={"good": good},
        run_id=uuid4(),
        audit=AuditLogger(tmp_path / "AUDIT.jsonl"),
        workspace_root=tmp_path / "ws",
        data_root=tmp_path,
        authorization_assertion=None,
        wire_egress=True,
    )

    observer(Seed(type=SeedType.DOMAIN, value="example.com"))
    assert len(sessions) == 1
    session = sessions[0]
    session.entries.append(SimpleNamespace(status=200))

    observer(Seed(type=SeedType.DOMAIN, value="example.org"))
    session.entries.append(SimpleNamespace(status=429))
    observer.close()

    # One session for the whole run: a second per-invocation session would
    # collide on the adapter-derived Docker network name.
    assert len(sessions) == 1
    assert session.started == 1
    assert session.stopped == 1
    assert good.calls == 2
    assert [entry.status for entry in chained[0]] == [200]
    assert [entry.status for entry in chained[1]] == [429]
    assert observer.egress_totals == {"total": 2, "allowed": 1, "refused": 1}


def test_adapter_observer_records_wiring_failures_without_crashing(tmp_path, monkeypatch) -> None:
    started: list[str] = []

    class _FailingSession:
        proxy_url = "http://proxy.invalid:8899"
        network = "aletheia-egress-net-bad"

        def __init__(self, adapter, log_dir, rate=1.0, capacity=1.0):
            self.adapter = adapter
            started.append(adapter)

        def start(self):
            raise RuntimeError("network aletheia-egress-net-bad already exists")

        def read_entries(self):
            return []

        def stop(self):
            pass

    _patch_egress(monkeypatch, _FailingSession)

    bad = _StubAdapter({SeedType.DOMAIN})
    bad.descriptor = SimpleNamespace(network_required=True)
    observer = AdapterObserver(
        adapters={"bad": bad},
        run_id=uuid4(),
        audit=AuditLogger(tmp_path / "AUDIT.jsonl"),
        workspace_root=tmp_path / "ws",
        data_root=tmp_path,
        authorization_assertion=None,
        wire_egress=True,
    )

    first = observer(Seed(type=SeedType.DOMAIN, value="example.com"))
    assert first.findings == ()
    assert "already exists" in first.blocked_reason
    assert bad.calls == 0

    second = observer(Seed(type=SeedType.DOMAIN, value="example.org"))
    assert len(started) == 1  # never retried
    assert bad.calls == 0  # never runs unwired
    assert "egress wiring failed earlier" in second.blocked_reason
    audit_text = (tmp_path / "AUDIT.jsonl").read_text(encoding="utf-8")
    assert audit_text.count("cascade_adapter_error") == 1
