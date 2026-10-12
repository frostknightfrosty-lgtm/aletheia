from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.phase5c import GravatarAdapter, RdapAdapter
from aletheia.adapters.registry import phase7_adapters
from aletheia.core.audit import AuditLogger
from aletheia.core.execution import DockerExecutionError
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "gravatar.json"
RDAP_FIXTURE = ROOT / "tests" / "fixtures" / "rdap.json"
EMAIL = "test@example.com"
EMAIL_HASH = hashlib.sha256(EMAIL.encode()).hexdigest()
EXCLUDED_FIELDS = {
    "contact_info", "payments", "links", "gallery", "verified_accounts",
    "section_visibility", "avatar_alt_text", "pronouns",
}


def _request(value: str = EMAIL, assertion: str | None = "authorized email investigation") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.EMAIL, value=value),
        legal_only=True, authorization_assertion=assertion,
    )


def _rdap_request(seed_type: SeedType, value: str) -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=seed_type, value=value), legal_only=True,
    )


def _load_runner():
    spec = importlib.util.spec_from_file_location("gravatar_runner", ROOT / "docker" / "gravatar" / "runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_rdap_runner():
    spec = importlib.util.spec_from_file_location("rdap_runner", ROOT / "docker" / "rdap" / "runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gravatar_and_rdap_are_registered():
    registry = phase7_adapters()
    assert "gravatar" in registry
    assert "rdap" in registry
    descriptor = registry["gravatar"].descriptor
    assert descriptor.input_types == [SeedType.EMAIL]
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.network_required is True
    assert descriptor.docker_image == "aletheia/gravatar:api-v3"
    rdap = registry["rdap"].descriptor
    assert rdap.input_types == [SeedType.DOMAIN, SeedType.IP]
    assert rdap.network_required is True
    assert rdap.docker_image == "aletheia/rdap:rfc9082"


def test_gravatar_requires_authorization_before_docker(monkeypatch, tmp_path):
    import aletheia.core.adapters as core_adapters
    called = False

    def fake_run_docker(**kwargs):
        nonlocal called
        called = True
        raise DockerExecutionError("must not execute")

    monkeypatch.setattr(core_adapters, "run_docker", fake_run_docker)
    with pytest.raises(ValueError, match="authorization_assertion"):
        GravatarAdapter().run(_request(assertion=None), tmp_path / "gravatar", AuditLogger(tmp_path / "audit.jsonl"))
    assert called is False


def test_gravatar_command_passes_only_hash_arguments_and_never_the_email():
    # The image ENTRYPOINT already supplies `python /opt/runner.py`; the command is arguments only.
    command = GravatarAdapter().build_command(_request(" Test@Example.com "), Path("."))
    assert command == ["hash", EMAIL_HASH]
    assert not any("@" in part for part in command)


@parser_test("gravatar")
def test_gravatar_parser_keeps_only_curated_fields():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = GravatarAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.entity_type == EntityType.SOCIAL_ACCOUNT
    assert finding.value == "https://gravatar.com/aletheia-synthetic-test"
    assert finding.attributes["email_sha256"] == EMAIL_HASH
    assert finding.attributes["display_name"] == "Synthetic Test Profile"
    assert not (EXCLUDED_FIELDS & set(finding.attributes))
    assert "is_organization" not in finding.attributes  # False is not emitted
    flattened = json.dumps(finding.attributes)
    assert "+1555" not in flattened and "0x0000" not in flattened and EMAIL not in flattened
    assert finding.provenance.source_url == f"https://api.gravatar.com/v3/profiles/{EMAIL_HASH}"
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(stdout.encode()).hexdigest()
    assert "not identity confirmation" in finding.provenance.notes[0]


def test_gravatar_parser_rejects_hash_mismatch_not_found_and_garbage():
    stdout = FIXTURE.read_text(encoding="utf-8")
    adapter = GravatarAdapter()
    assert not adapter.parse(_request("different@example.com"), Path("."), stdout, "", 0).findings
    assert not adapter.parse(_request(), Path("."), json.dumps({"http_status": 404, "status": "not_found"}), "", 0).findings
    assert not adapter.parse(_request(), Path("."), "not json", "", 0).findings
    assert not adapter.parse(_request(), Path("."), "", "", 4).findings


def test_gravatar_parser_drops_non_https_urls():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["avatar_url"] = "http://0.gravatar.com/avatar/x"
    kept = GravatarAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert "avatar_url" not in kept.findings[0].attributes
    payload["profile_url"] = "javascript:alert(1)"
    assert not GravatarAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0).findings


def test_gravatar_runner_curates_before_output():
    runner = _load_runner()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    curated = runner.curate(payload, EMAIL_HASH)
    assert curated is not None
    assert set(curated) <= {"hash", "profile_url", "avatar_url", "display_name", "location",
                            "description", "job_title", "company", "is_organization"}
    assert not (EXCLUDED_FIELDS & set(curated))
    assert runner.curate(payload, "0" * 64) is None
    assert runner.curate(["not", "a", "dict"], EMAIL_HASH) is None


def test_gravatar_runner_argument_validation(monkeypatch, capsys):
    runner = _load_runner()
    for argv in (["runner.py"], ["runner.py", "hash"], ["runner.py", "hash", EMAIL],
                 ["runner.py", "email", EMAIL_HASH], ["runner.py", "hash", EMAIL_HASH.upper()]):
        monkeypatch.setattr("sys.argv", argv)
        assert runner.main() == 2
    monkeypatch.setattr("sys.argv", ["runner.py", "--health"])
    assert runner.main() == 0
    assert capsys.readouterr().out.strip().endswith("ok")


@parser_test("rdap")
def test_rdap_domain_parser_normalizes_seed_and_keeps_curated_registry_fields():
    fixture = json.loads(RDAP_FIXTURE.read_text(encoding="utf-8"))
    stdout = json.dumps(fixture["domain"], sort_keys=True)
    request = _rdap_request(SeedType.DOMAIN, "HTTPS://Example.COM./details/path")
    result = RdapAdapter().parse(request, Path("."), stdout, "", 0)
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.entity_type == EntityType.DOMAIN
    assert finding.value == "example.com"
    assert finding.attributes["ldhName"] == "EXAMPLE.COM"
    assert finding.attributes["nameservers"] == ["ns1.example.net", "ns2.example.net"]
    assert finding.attributes["dnssec_delegation_signed"] is True
    assert "entities" not in finding.attributes and "remarks" not in finding.attributes
    assert finding.provenance.source_url == fixture["domain"]["query_url"]
    assert finding.provenance.confidence == 0.85
    assert "registry-data confidence only" in finding.provenance.notes[0].lower()
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(stdout.encode()).hexdigest()


def test_rdap_ip_parser_requires_matching_address_range_and_emits_registry_confidence():
    fixture = json.loads(RDAP_FIXTURE.read_text(encoding="utf-8"))
    stdout = json.dumps(fixture["ip"], sort_keys=True)
    request = _rdap_request(SeedType.IP, "192.0.2.7")
    result = RdapAdapter().parse(request, Path("."), stdout, "", 0)
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.entity_type == EntityType.IP
    assert finding.value == "192.0.2.7"
    assert finding.attributes["network_name"] == "Documentation Network"
    assert "entities" not in finding.attributes and "remarks" not in finding.attributes
    assert finding.provenance.confidence == 0.85
    assert "not proof of control or identity" in finding.provenance.notes[0]


def test_rdap_command_normalizes_domain_and_passes_arguments_only():
    adapter = RdapAdapter()
    domain = _rdap_request(SeedType.DOMAIN, "https://Example.COM./one/two")
    ip = _rdap_request(SeedType.IP, "192.0.2.7")
    assert adapter.build_command(domain, Path(".")) == ["domain", "example.com"]
    assert adapter.build_command(ip, Path(".")) == ["ip", "192.0.2.7"]


def test_rdap_parser_rejects_mismatched_records_and_urls():
    fixture = json.loads(RDAP_FIXTURE.read_text(encoding="utf-8"))
    domain_payload = fixture["domain"]
    domain_payload["record"]["ldhName"] = "elsewhere.example"
    result = RdapAdapter().parse(
        _rdap_request(SeedType.DOMAIN, "example.com"), Path("."), json.dumps(domain_payload), "", 0,
    )
    assert not result.findings
    assert "did not match" in result.stderr_tail

    ip_payload = fixture["ip"]
    ip_payload["query_url"] = "https://rdap.example/ip/192.0.2.99"
    result = RdapAdapter().parse(
        _rdap_request(SeedType.IP, "192.0.2.7"), Path("."), json.dumps(ip_payload), "", 0,
    )
    assert not result.findings
    assert "did not match" in result.stderr_tail


def test_rdap_runner_normalizes_url_and_uses_one_exact_iana_bootstrap_and_lookup(monkeypatch):
    runner = _load_rdap_runner()
    fixture = json.loads(RDAP_FIXTURE.read_text(encoding="utf-8"))
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if url == runner.BOOTSTRAP_URLS["domain"]:
            return {"services": [[["com"], ["https://rdap.example/rdap/"]]]}
        if url == "https://rdap.example/rdap/domain/example.com":
            return fixture["domain"]["record"]
        raise AssertionError(f"unexpected request URL: {url}")

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch)
    result, reason, code = runner.lookup("domain", "HTTPS://Example.COM./path")
    assert code == 0 and reason is None
    assert calls == [runner.BOOTSTRAP_URLS["domain"], "https://rdap.example/rdap/domain/example.com"]
    assert result["query_url"] == calls[-1]
    assert "entities" not in result["record"] and "remarks" not in result["record"]


def test_rdap_runner_uses_address_family_bootstrap_and_exact_ip_lookup(monkeypatch):
    runner = _load_rdap_runner()
    fixture = json.loads(RDAP_FIXTURE.read_text(encoding="utf-8"))
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if url == runner.BOOTSTRAP_URLS["ipv4"]:
            return {"services": [[["192.0.2.0/24"], ["https://rdap.example/rdap/"]]]}
        if url == "https://rdap.example/rdap/ip/192.0.2.7":
            return fixture["ip"]["record"]
        raise AssertionError(f"unexpected request URL: {url}")

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch)
    result, reason, code = runner.lookup("ip", "192.0.2.7")
    assert code == 0 and reason is None
    assert calls == [runner.BOOTSTRAP_URLS["ipv4"], "https://rdap.example/rdap/ip/192.0.2.7"]
    assert result["query_url"] == calls[-1]
    assert result["record"]["startAddress"] == "192.0.2.0"
    assert "entities" not in result["record"]


def test_rdap_runner_invalid_ip_returns_empty_result_and_reason_without_network(monkeypatch, capsys):
    runner = _load_rdap_runner()
    monkeypatch.setattr(runner, "_fetch_json", lambda _url: pytest.fail("invalid IP must not access network"))
    code = runner.main(["ip", "not-an-ip-address"])
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out) == {"reason": "invalid_ip_seed", "status": "empty"}
    assert "invalid_ip_seed" in captured.err


def test_rdap_runner_health_is_offline(capsys):
    runner = _load_rdap_runner()
    assert runner.main(["--health"]) == 0
    assert capsys.readouterr().out.strip() == "ok"
