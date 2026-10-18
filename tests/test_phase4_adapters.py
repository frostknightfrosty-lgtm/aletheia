import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.identity import (
    H8mailAdapter, HIBPAdapter, HoleheAdapter, LibPhoneNumberAdapter,
    MaigretAdapter, PhoneInfogaAdapter, XposedOrNotAdapter,
)
from aletheia.adapters.registry import phase4_adapters
from aletheia.core.audit import AuditLogger
from aletheia.core.execution import DockerExecutionError
from aletheia.core.models import AdapterRunRequest, Seed, SeedType, EntityType


def req(kind, value, assertion="authorized personal-identifier investigation"):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=kind, value=value), legal_only=True,
                             authorization_assertion=assertion)


def test_phase4_registry_contains_seven_new_adapters():
    registry = phase4_adapters()
    expected = {"maigret", "holehe", "h8mail", "hibp", "xposedornot", "phoneinfoga", "libphonenumber"}
    assert expected <= set(registry)
    assert len(registry) == 19


def test_personal_identifier_adapters_require_authorization_before_docker(monkeypatch, tmp_path):
    import aletheia.core.adapters as core_adapters
    called = False

    def fake_run_docker(**kwargs):
        nonlocal called
        called = True
        raise DockerExecutionError("must not execute")

    monkeypatch.setattr(core_adapters, "run_docker", fake_run_docker)
    for adapter, kind, value in [
        (MaigretAdapter(), SeedType.USERNAME, "alice"),
        (HoleheAdapter(), SeedType.EMAIL, "alice@example.com"),
        (H8mailAdapter(), SeedType.EMAIL, "alice@example.com"),
        (HIBPAdapter(), SeedType.EMAIL, "alice@example.com"),
        (XposedOrNotAdapter(), SeedType.EMAIL, "alice@example.com"),
        (PhoneInfogaAdapter(), SeedType.PHONE, "+14155552671"),
    ]:
        request = AdapterRunRequest(
            run_id=uuid4(),
            seed=Seed(type=kind, value=value),
            legal_only=True,
            authorization_assertion=None,
        )
        with pytest.raises(ValueError, match="authorization_assertion"):
            adapter.run(request, tmp_path / adapter.descriptor.name, AuditLogger(tmp_path / "audit.jsonl"))
    assert called is False


@parser_test('maigret')
def test_maigret_parser_only_accepts_claimed_results(tmp_path):
    p = tmp_path / "results"
    p.mkdir()
    (p / "alice.ndjson").write_text(
        json.dumps({"site": "GitHub", "url_user": "https://github.com/alice", "status": {"status": "Claimed"}}) + "\n"
        + json.dumps({"site": "Example", "url_user": "https://example.com/alice", "status": {"status": "Available"}}) + "\n",
        encoding="utf-8",
    )
    result = MaigretAdapter().parse(req(SeedType.USERNAME, "alice"), tmp_path, "", "", 0)
    assert {f.value for f in result.findings if f.entity_type == EntityType.URL} == {"https://github.com/alice"}


def test_maigret_command_survives_a_read_only_root_and_leaves_the_transport_to_env():
    adapter = MaigretAdapter()
    plain = adapter.build_command(req(SeedType.USERNAME, "alice"), Path("."))
    # The autoupdate check creates ~/.maigret, which a --read-only container
    # cannot do (live run 39125383530 crashed there before any site was checked).
    assert "--no-autoupdate" in plain
    assert "--proxy" not in plain

    request = AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=SeedType.USERNAME, value="alice"),
        legal_only=True,
        authorization_assertion="authorized personal-identifier investigation",
        proxy_url="http://aletheia-egress-maigret:8888",
    )
    proxied = adapter.build_command(request, Path("."))
    # The proxy is injected via HTTP_PROXY/HTTPS_PROXY in the container
    # environment (core.execution). An explicit --proxy flag made maigret
    # 0.6.6's aiohttp transport tunnel to the proxy through the proxy itself
    # (live run 39135219248: 455 self-CONNECTs, 46% "Proxy" errors); the
    # env-only path is single-hop for both transports.
    assert "--proxy" not in proxied
    assert "--dns-resolver" in proxied


@parser_test('holehe')
def test_holehe_parser_retains_positive_signals():
    stdout = "[+] twitter : account exists\n[-] instagram : not found\n[+] github : registered\n"
    result = HoleheAdapter().parse(req(SeedType.EMAIL, "alice@example.com"), Path("."), stdout, "", 0)
    assert {f.value for f in result.findings} == {"twitter", "github"}


@parser_test('h8mail')
def test_h8mail_parser_does_not_emit_password_fields(tmp_path):
    payload = {"results": [{"source": "HIBP", "breach": "ExampleBreach", "password": "secret"}]}
    (tmp_path / "h8mail.json").write_text(json.dumps(payload), encoding="utf-8")
    result = H8mailAdapter().parse(req(SeedType.EMAIL, "alice@example.com"), tmp_path, "", "", 0)
    assert all(f.attributes.get("password") is None for f in result.findings)
    assert "ExampleBreach" in {f.value for f in result.findings}


@parser_test('hibp')
def test_hibp_parser_creates_breach_findings():
    payload = json.dumps([{"Name": "Example Breach", "Title": "Example", "Domain": "example.com"}])
    result = HIBPAdapter().parse(req(SeedType.EMAIL, "alice@example.com"), Path("."), payload, "", 0)
    assert [(f.entity_type, f.value) for f in result.findings] == [(EntityType.BREACH, "Example Breach")]


@parser_test('xposedornot')
def test_xposedornot_parser_reads_only_breach_names():
    payload = Path(__file__).parent / "fixtures" / "xposedornot.json"
    result = XposedOrNotAdapter().parse(
        req(SeedType.EMAIL, "test@example.com"), Path("."), payload.read_text(encoding="utf-8"), "", 0
    )
    assert {f.value for f in result.findings} == {
        "Tesco", "KiwiFarms", "Vermillion", "Verified", "LizardSquad",
        "2fast4u", "Autotrader", "MyRepoSpace", "SweClockers",
    }
    assert all("password" not in f.attributes for f in result.findings)
    mismatched = XposedOrNotAdapter().parse(
        req(SeedType.EMAIL, "different@example.com"), Path("."), payload.read_text(encoding="utf-8"), "", 0
    )
    assert not mismatched.findings


@parser_test('libphonenumber')
def test_libphonenumber_parser():
    payload = json.dumps({"e164": "+14155552671", "region": "US", "valid": True, "possible": True})
    result = LibPhoneNumberAdapter().parse(req(SeedType.PHONE, "+1 415 555 2671"), Path("."), payload, "", 0)
    assert any(f.entity_type == EntityType.PHONE and f.value == "+14155552671" for f in result.findings)


@parser_test('phoneinfoga')
def test_phoneinfoga_parser():
    stdout = "Number: +14155552671\nCountry: United States\nCarrier: Example Carrier\n"
    result = PhoneInfogaAdapter().parse(req(SeedType.PHONE, "+14155552671"), Path("."), stdout, "", 0)
    assert any(f.entity_type == EntityType.PHONE for f in result.findings)
    assert any(f.value == "Example Carrier" for f in result.findings)


def test_personal_identifier_seed_types_are_typed():
    assert Seed(type=SeedType.EMAIL, value="a@example.com").type == SeedType.EMAIL
    assert Seed(type=SeedType.PHONE, value="+14155552671").type == SeedType.PHONE
