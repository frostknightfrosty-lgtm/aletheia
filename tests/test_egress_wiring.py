"""Unit tests for the Phase 12 egress wiring.

These cover the pure command builders and the ``ProxySession`` lifecycle with an
injected runner, so no Docker daemon is required. The end-to-end scenario that
actually launches containers lives in ``ci/egress_scenario.py`` and is exercised
by ``tests/test_docker_integration.py`` under CI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from aletheia.core import egress
from aletheia.core.adapters import Adapter
from aletheia.core.execution import run_docker
from aletheia.core.models import (
    AdapterDescriptor,
    AdapterRunRequest,
    AdapterRunResult,
    EntityType,
    Seed,
    SeedType,
)


class _Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _recorder(returncode: int = 0):
    calls: list[list[str]] = []

    def runner(argv: list[str]):
        calls.append(list(argv))
        return _Completed(returncode=returncode)

    return calls, runner


# -- the wiring policy ---------------------------------------------------------


def test_every_network_adapter_is_wired_and_no_other_is():
    """Phase 15: coverage is a policy, not an allowlist.

    Every adapter whose descriptor declares ``network_required=True`` must be
    wired; an adapter that declares it does not need the network must not be,
    because wiring it would build an ``--internal`` network for a container that
    never egresses. This runs against the real registry, so an adapter added in a
    later phase is covered the moment it declares its network need.
    """
    from aletheia.adapters.registry import phase7_adapters

    adapters = phase7_adapters()
    assert len(adapters) == 49, "registry size is the denominator for coverage"

    wired = {
        name
        for name, adapter in adapters.items()
        if egress.is_wired(name, network_required=adapter.descriptor.network_required)
    }
    expected = {name for name, adapter in adapters.items() if adapter.descriptor.network_required}

    assert wired == expected
    # The three adapters Phase 12 hand-wired are now a strict subset of coverage.
    assert {"search_engines", "ssl_tls", "ip_intelligence"} <= wired
    assert len(wired) > 3, "Phase 15 must cover more than the Phase 12 subset"


def test_the_exempt_list_is_empty_and_actually_excludes(monkeypatch):
    assert egress.EGRESS_EXEMPT_ADAPTERS == ()
    # Proving the exemption has an effect, not just that the tuple is empty:
    # an exclusion is a recorded decision that must change the outcome.
    monkeypatch.setattr(egress, "EGRESS_EXEMPT_ADAPTERS", ("search_engines",))
    assert egress.is_wired("search_engines", network_required=True) is False
    assert egress.is_wired("ssl_tls", network_required=True) is True


def test_network_and_container_names_are_dns_safe():
    assert egress.network_name("search_engines") == "aletheia-egress-net-search-engines"
    # Underscores cannot appear in DNS labels, so container_name sanitizes them.
    assert egress.EgressProxy("search_engines").container_name == "aletheia-egress-search-engines"
    assert egress.EgressProxy("search_engines").proxy_url == "http://aletheia-egress-search-engines:8888"


def test_create_network_is_internal():
    assert egress.create_network_command("net") == ["docker", "network", "create", "--internal", "net"]
    assert egress.remove_network_command("net") == ["docker", "network", "rm", "net"]


# -- proxy run command options -------------------------------------------------


def test_detached_proxy_run_command_omits_host_port(tmp_path):
    command = egress.EgressProxy("search_engines").run_command(
        log_dir=tmp_path, network="net", detached=True, publish_port=False
    )
    assert command[:3] == ["docker", "run", "--rm"]
    assert "-d" in command
    assert "--name" in command and "aletheia-egress-search-engines" in command
    assert command[command.index("--network") + 1] == "net"
    # In-network wiring never publishes a host port.
    assert "-p" not in command


# -- ProxySession lifecycle (injected runner) ----------------------------------


def test_session_starts_network_then_detached_proxy(tmp_path):
    calls, runner = _recorder()
    session = egress.ProxySession("ssl_tls", tmp_path / "egress", runner=runner)

    session.start()

    assert calls[0] == ["docker", "network", "create", "--internal", "aletheia-egress-net-ssl-tls"]
    assert calls[1][:3] == ["docker", "run", "--rm"]
    assert "-d" in calls[1]
    assert calls[1].count("--network") == 1
    assert "aletheia-egress-ssl-tls" in calls[1]
    assert f"{(tmp_path / 'egress').resolve()}:/var/log/aletheia" in calls[1]
    assert "ALETHEIA_EGRESS_RATE=1.0" in calls[1]
    assert "ALETHEIA_EGRESS_BURST=1.0" in calls[1]
    assert session.proxy_url == "http://aletheia-egress-ssl-tls:8888"
    assert session.network == "aletheia-egress-net-ssl-tls"
    assert session.log_path == tmp_path / "egress" / egress.LOG_FILENAME


def test_session_forwards_operator_egress_limits(tmp_path):
    """Run 39119306001 exposed that wide sweeps need more than 1 request/second.

    The proxy answers 429 over the limit instead of queueing, so the operator's
    ``--egress-rate``/``--egress-burst`` must reach the proxy environment.
    """
    calls, runner = _recorder()
    session = egress.ProxySession(
        "sherlock", tmp_path / "egress", rate=20.0, capacity=100.0, runner=runner
    )

    session.start()

    assert "ALETHEIA_EGRESS_RATE=20.0" in calls[1]
    assert "ALETHEIA_EGRESS_BURST=100.0" in calls[1]


def test_session_context_manager_stops_proxy_and_network(tmp_path):
    calls, runner = _recorder()
    with egress.ProxySession("ip_intelligence", tmp_path / "egress", runner=runner) as session:
        assert session.proxy_container == "aletheia-egress-ip-intelligence"

    assert ["docker", "rm", "-f", "aletheia-egress-ip-intelligence"] in calls
    assert ["docker", "network", "rm", "aletheia-egress-net-ip-intelligence"] in calls


def test_session_raises_when_a_command_fails(tmp_path):
    calls, runner = _recorder(returncode=1)
    session = egress.ProxySession("search_engines", tmp_path / "egress", runner=runner)
    with pytest.raises(egress.DockerCommandError):
        session.start()


def test_session_stop_never_raises(tmp_path):
    def failing_runner(argv):
        raise OSError("docker exploded")

    session = egress.ProxySession("search_engines", tmp_path / "egress", runner=failing_runner)
    session.stop()  # must swallow the failure


# -- run_docker joins the internal network -------------------------------------


def test_run_docker_joins_named_network(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _Completed()

    monkeypatch.setattr("subprocess.run", fake_run)
    run_docker(
        image="aletheia/search-engines:v1",
        command=["runner.py", "name", "example"],
        workspace=tmp_path,
        timeout_seconds=5,
        proxy_url="http://aletheia-egress-search-engines:8888",
        network=True,
        network_name="aletheia-egress-net-search-engines",
    )
    argv = captured["argv"]
    # The named network wins over the boolean "network" flag.
    assert argv[argv.index("--network") + 1] == "aletheia-egress-net-search-engines"
    assert "HTTP_PROXY=http://aletheia-egress-search-engines:8888" in argv


# -- orchestrator wiring -------------------------------------------------------


class _RecordingAdapter(Adapter):
    def __init__(self, name: str, *, network_required: bool = True) -> None:
        self.descriptor = AdapterDescriptor(
            name=name,
            license="project-internal",
            input_types=[SeedType.DOMAIN],
            output_types=[EntityType.DOMAIN],
            legal_notes=[],
            rate_limit="n/a",
            invocation="test",
            version_pin="v1",
            upstream="https://example.invalid",
            network_required=network_required,
            docker_image="aletheia/test:v1",
        )
        self.requests: list[AdapterRunRequest] = []

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.DOMAIN

    def build_command(self, request, workspace):
        return ["runner.py"]

    def parse(self, request, workspace, stdout, stderr, exit_code):
        raise AssertionError("parse is not called by this test adapter")

    def run(self, request, workspace, audit):
        self.requests.append(request)
        workspace.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="ok",
            started_at=now,
            finished_at=now,
        )


def _fake_sessions(monkeypatch):
    events: list[str] = []

    class _FakeSession:
        def __init__(self, adapter, log_dir, **kwargs):
            self.adapter = adapter
            events.append(f"init:{adapter}")

        def start(self):
            events.append(f"start:{self.adapter}")
            return self

        @property
        def proxy_url(self):
            return f"http://aletheia-egress-{self.adapter}:8888"

        @property
        def network(self):
            return f"aletheia-egress-net-{self.adapter}"

        def read_entries(self):
            return []

        def stop(self):
            events.append(f"stop:{self.adapter}")

    monkeypatch.setattr(egress, "ProxySession", _FakeSession)
    return events


def test_orchestrator_wires_a_network_adapter_by_default(tmp_path, monkeypatch):
    """No flag needed: a network-requiring adapter is wired by default."""
    from aletheia.core.orchestrator import Orchestrator

    events = _fake_sessions(monkeypatch)
    orchestrator = Orchestrator(tmp_path)
    adapter = _RecordingAdapter("search_engines")
    orchestrator.adapters = {"search_engines": adapter}
    run_id = orchestrator.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))

    orchestrator.resume(run_id)

    assert events == ["init:search_engines", "start:search_engines", "stop:search_engines"]
    request = adapter.requests[0]
    assert request.proxy_url == "http://aletheia-egress-search_engines:8888"
    assert request.network_name == "aletheia-egress-net-search_engines"


def test_orchestrator_leaves_a_network_free_adapter_alone(tmp_path, monkeypatch):
    """An adapter that needs no network gets no proxy and no internal network."""
    from aletheia.core.orchestrator import Orchestrator

    events = _fake_sessions(monkeypatch)
    orchestrator = Orchestrator(tmp_path)
    adapter = _RecordingAdapter("local_only", network_required=False)
    orchestrator.adapters = {"local_only": adapter}
    run_id = orchestrator.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))

    orchestrator.resume(run_id)

    assert events == []
    request = adapter.requests[0]
    assert request.proxy_url is None
    assert request.network_name is None


def test_orchestrator_can_disable_wiring_for_offline_replays(tmp_path, monkeypatch):
    """``wire_egress=False`` keeps a network adapter off Docker networking.

    The offline replay paths use this so a machine without Docker, or a run that
    must not create containers, still works.
    """
    from aletheia.core.orchestrator import Orchestrator

    events = _fake_sessions(monkeypatch)
    orchestrator = Orchestrator(tmp_path)
    adapter = _RecordingAdapter("search_engines")
    orchestrator.adapters = {"search_engines": adapter}
    run_id = orchestrator.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))

    orchestrator.resume(run_id, wire_egress=False)

    assert events == []
    request = adapter.requests[0]
    assert request.proxy_url is None
    assert request.network_name is None


def test_orchestrator_forwards_egress_limits_to_the_session(tmp_path, monkeypatch):
    """The operator's --egress-rate/--egress-burst reach the proxy session.

    Run 39119306001 was the first live run; the default 1 request/second makes
    wide sweeps collect 429s, so the limits must be selectable per run while
    the default stays unchanged.
    """
    from aletheia.core.orchestrator import Orchestrator

    recorded: list[dict] = []

    class _RecordingSession:
        def __init__(self, adapter, log_dir, **kwargs):
            recorded.append(kwargs)

        def start(self):
            return self

        @property
        def proxy_url(self):
            return "http://aletheia-egress-search_engines:8888"

        @property
        def network(self):
            return "aletheia-egress-net-search_engines"

        def read_entries(self):
            return []

        def stop(self):
            pass

    monkeypatch.setattr(egress, "ProxySession", _RecordingSession)
    orchestrator = Orchestrator(tmp_path)
    orchestrator.adapters = {"search_engines": _RecordingAdapter("search_engines")}

    raised_run = orchestrator.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))
    orchestrator.resume(raised_run, egress_rate=20.0, egress_burst=100.0)
    assert (recorded[0]["rate"], recorded[0]["capacity"]) == (20.0, 100.0)

    recorded.clear()
    default_run = orchestrator.create_run(Seed(type=SeedType.DOMAIN, value="example.org"))
    orchestrator.resume(default_run)
    assert (recorded[0]["rate"], recorded[0]["capacity"]) == (1.0, 1.0)


# -- CI scenario ---------------------------------------------------------------


def test_ci_egress_scenario_policy_check_matches_the_registry():
    """The CI scenario must report the policy check under the name CI asserts.

    Run 39083768809 proved the assertion in tests/test_docker_integration.py works:
    the scenario computed this check but main() overwrote it before printing, so
    the run failed on a missing name. The summary is now assembled in one place;
    this pins the check itself.
    """
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "ci" / "egress_scenario.py"
    spec = importlib.util.spec_from_file_location("aletheia_egress_scenario", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    check = module._policy_check()
    assert check["name"] == "phase15-egress-policy-covers-registry"
    assert check["ok"], check["detail"]


# -- CLI -----------------------------------------------------------------------


def test_cli_resume_passes_the_egress_decision_through(monkeypatch, tmp_path):
    """``--no-egress-proxy`` is the operator's only way to opt out."""
    import sys

    from aletheia.cli import main as cli

    calls: list[dict] = []

    class _FakeOrchestrator:
        def __init__(self, data_dir):
            self.data_dir = data_dir

        def resume(self, run_id, **kwargs):
            calls.append(kwargs)
            return {}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)

    for extra, expected in (([], True), (["--no-egress-proxy"], False)):
        calls.clear()
        monkeypatch.setattr(
            sys,
            "argv",
            ["aletheia", "resume", "--run-id", str(uuid4()), "--data-dir", str(tmp_path), *extra],
        )
        cli.main()
        assert calls[0]["wire_egress"] is expected, (extra, calls)


def test_cli_resume_passes_the_egress_limits_through(monkeypatch, tmp_path):
    """Run 39119306001: wide sweeps need a selectable per-adapter rate limit.

    The proxy answers 429 over the limit, so the operator must be able to raise
    it per run; the default stays the polite 1 request/second.
    """
    import sys

    from aletheia.cli import main as cli

    calls: list[dict] = []

    class _FakeOrchestrator:
        def __init__(self, data_dir):
            self.data_dir = data_dir

        def resume(self, run_id, **kwargs):
            calls.append(kwargs)
            return {}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)

    monkeypatch.setattr(
        sys,
        "argv",
        ["aletheia", "resume", "--run-id", str(uuid4()), "--data-dir", str(tmp_path),
         "--egress-rate", "20", "--egress-burst", "100"],
    )
    cli.main()
    assert calls[0]["egress_rate"] == 20.0
    assert calls[0]["egress_burst"] == 100.0

    calls.clear()
    monkeypatch.setattr(
        sys,
        "argv",
        ["aletheia", "resume", "--run-id", str(uuid4()), "--data-dir", str(tmp_path)],
    )
    cli.main()
    assert (calls[0]["egress_rate"], calls[0]["egress_burst"]) == (1.0, 1.0)
