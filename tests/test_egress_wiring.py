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


# -- the wired set -------------------------------------------------------------


def test_only_the_representative_subset_is_wired():
    assert egress.EGRESS_WIRED_ADAPTERS == ("search_engines", "ssl_tls", "ip_intelligence")
    for name in egress.EGRESS_WIRED_ADAPTERS:
        assert egress.is_wired(name)
    # A representative unwired adapter is untouched.
    assert not egress.is_wired("rdap")
    assert not egress.is_wired("leak_checkers")


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
    assert f"{tmp_path / 'egress'}:/var/log/aletheia" in calls[1]
    assert session.proxy_url == "http://aletheia-egress-ssl-tls:8888"
    assert session.network == "aletheia-egress-net-ssl-tls"
    assert session.log_path == tmp_path / "egress" / egress.LOG_FILENAME


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
    def __init__(self, name: str) -> None:
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
            network_required=True,
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


def test_orchestrator_wires_a_wired_adapter(tmp_path, monkeypatch):
    from aletheia.core.orchestrator import Orchestrator

    events = _fake_sessions(monkeypatch)
    orchestrator = Orchestrator(tmp_path)
    adapter = _RecordingAdapter("search_engines")
    orchestrator.adapters = {"search_engines": adapter}
    run_id = orchestrator.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))

    orchestrator.resume(run_id, wire_egress=True)

    assert events == ["init:search_engines", "start:search_engines", "stop:search_engines"]
    request = adapter.requests[0]
    assert request.proxy_url == "http://aletheia-egress-search_engines:8888"
    assert request.network_name == "aletheia-egress-net-search_engines"


def test_orchestrator_leaves_an_unwired_adapter_alone(tmp_path, monkeypatch):
    from aletheia.core.orchestrator import Orchestrator

    events = _fake_sessions(monkeypatch)
    orchestrator = Orchestrator(tmp_path)
    adapter = _RecordingAdapter("rdap")
    orchestrator.adapters = {"rdap": adapter}
    run_id = orchestrator.create_run(Seed(type=SeedType.DOMAIN, value="example.com"))

    orchestrator.resume(run_id, wire_egress=True)

    assert events == []
    request = adapter.requests[0]
    assert request.proxy_url is None
    assert request.network_name is None
