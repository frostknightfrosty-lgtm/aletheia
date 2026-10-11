from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.infra import (
    AmassAdapter, AssetfinderAdapter, CrtshAdapter, DnsreconAdapter,
    DnsxAdapter, FierceAdapter, MassdnsAdapter, ShodanAdapter, SubfinderAdapter,
)
from aletheia.adapters.registry import phase3_adapters
from aletheia.core.audit import AuditLogger
from aletheia.core.execution import DockerExecutionError
from aletheia.core.models import AdapterRunRequest, Seed, SeedType


def req(seed_type=SeedType.DOMAIN, value="example.com", assertion=None):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=seed_type, value=value),
                             legal_only=True, authorization_assertion=assertion)


def test_phase3_registry_has_nine_new_adapters():
    registry = phase3_adapters()
    expected = {"amass", "subfinder", "assetfinder", "dnsx", "massdns", "dnsrecon", "fierce", "shodan", "crt.sh"}
    assert expected <= set(registry)
    assert len(registry) == 12


def test_new_descriptors_have_contract_fields():
    for adapter in [AmassAdapter(), SubfinderAdapter(), AssetfinderAdapter(), DnsxAdapter(),
                    MassdnsAdapter(), DnsreconAdapter(), FierceAdapter(), ShodanAdapter(),
                    CrtshAdapter()]:
        d = adapter.descriptor
        assert d.name and d.license and d.version_pin and d.docker_image
        assert d.input_types and d.output_types
        assert d.legal_notes and d.rate_limit and d.invocation
        assert isinstance(d.output_schema, dict)
        assert d.health_check


def test_active_adapters_require_authorization_before_docker(monkeypatch, tmp_path):
    import aletheia.core.adapters as core_adapters
    called = False

    def fake_run_docker(**kwargs):
        nonlocal called
        called = True
        raise DockerExecutionError("should not be called")

    monkeypatch.setattr(core_adapters, "run_docker", fake_run_docker)
    for adapter in [DnsxAdapter(), MassdnsAdapter(), DnsreconAdapter(), FierceAdapter()]:
        with pytest.raises(ValueError, match="authorization_assertion"):
            adapter.run(req(), tmp_path / adapter.descriptor.name, AuditLogger(tmp_path / "audit.jsonl"))
    assert called is False


@parser_test('subfinder')
def test_subfinder_parser_deduplicates_hosts(tmp_path):
    result = SubfinderAdapter().parse(req(), tmp_path, "a.example.com\nA.example.com\nnot-host\n", "", 0)
    assert [f.value for f in result.findings] == ["a.example.com"]


@parser_test('amass')
def test_amass_parser_detects_ip_and_host(tmp_path):
    result = AmassAdapter().parse(req(), tmp_path, "mail.example.com\n1.2.3.4\n", "", 0)
    assert {f.value for f in result.findings} == {"mail.example.com", "1.2.3.4"}


@parser_test('dnsx')
def test_dnsx_json_parser(tmp_path):
    (tmp_path / "dnsx.jsonl").write_text(
        '{"host":"example.com","a":["1.2.3.4"],"cname":["alias.example.net"],"txt":["v=spf1"]}\n',
        encoding="utf-8")
    result = DnsxAdapter().parse(req(assertion="I am authorized to query this target"), tmp_path, "", "", 0)
    assert {f.value for f in result.findings} >= {"example.com", "1.2.3.4", "alias.example.net", "v=spf1"}


@parser_test('massdns')
def test_massdns_parser():
    result = MassdnsAdapter().parse(req(assertion="authorized"), Path("."),
                                    "example.com. IN A\nexample.com. 60 IN A 1.2.3.4\n", "", 0)
    assert {f.value for f in result.findings} >= {"example.com", "1.2.3.4"}


@parser_test('shodan')
def test_shodan_domain_parser(tmp_path):
    payload = '{"data":[{"subdomain":"www","value":"1.2.3.4","type":"A"}]}'
    result = ShodanAdapter().parse(req(), tmp_path, payload, "", 0)
    assert {f.value for f in result.findings} >= {"example.com", "www.example.com", "1.2.3.4"}


@parser_test('crt.sh')
def test_crtsh_parser_scopes_names(tmp_path):
    payload = '[{"name_value":"example.com\\nwww.example.com\\nother.example.net","id":"1"}]'
    result = CrtshAdapter().parse(req(), tmp_path, payload, "", 0)
    assert {f.value for f in result.findings} >= {"example.com", "www.example.com"}
    assert "other.example.net" not in {f.value for f in result.findings}


@parser_test('assetfinder')
def test_assetfinder_parser_fixture(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "assetfinder.txt"
    payload = fixture.read_text(encoding="utf-8")
    result = AssetfinderAdapter().parse(req(), tmp_path, payload, "", 0)
    assert {f.value for f in result.findings} == {"www.example.com", "api.example.com"}


@parser_test('dnsrecon')
def test_dnsrecon_parser_fixture(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "dnsrecon.json"
    (tmp_path / "dnsrecon.json").write_bytes(fixture.read_bytes())
    result = DnsreconAdapter().parse(
        req(assertion="authorized"), tmp_path, "", "", 0
    )
    values = {f.value for f in result.findings}
    assert {"www.example.com", "192.0.2.10", "api.example.com", "app.example.com"} <= values
    assert "bad.other.net" in values  # parser scope is provenance, not target filtering


@parser_test('fierce')
def test_fierce_parser_fixture(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "fierce.txt"
    payload = fixture.read_text(encoding="utf-8")
    result = FierceAdapter().parse(req(assertion="authorized"), tmp_path, payload, "", 0)
    values = {f.value for f in result.findings}
    assert {"www.example.com", "api.example.com", "192.0.2.10", "192.0.2.11"} <= values
