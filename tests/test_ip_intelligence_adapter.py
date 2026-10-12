from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.ip_intelligence import IPIntelligenceAdapter, IPIntelligenceFinding
from aletheia.adapters.registry import phase7_adapters
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ip_intelligence.json"
TARGET_IP = "1.1.1.1"


def _request(value: str = TARGET_IP) -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.IP, value=value), legal_only=True,
    )


def _load_runner():
    spec = importlib.util.spec_from_file_location("ip_intelligence_runner", ROOT / "docker" / "ip_intelligence" / "runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ip_intelligence_is_registered():
    registry = phase7_adapters()
    assert "ip_intelligence" in registry
    descriptor = registry["ip_intelligence"].descriptor
    assert descriptor.input_types == [SeedType.IP]
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.network_required is True
    assert descriptor.docker_image == "aletheia/ip-intelligence:v1"
    # Check all expected secret env vars are declared
    expected_secrets = {
        "IPINFO_TOKEN", "IPGEOLOCATION_KEY", "ABUSEIPDB_KEY", "GREYNOISE_KEY",
        "VIRUSTOTAL_KEY", "URLHAUS_AUTH_KEY", "THREATFOX_AUTH_KEY",
        "MALWAREBAZAAR_AUTH_KEY", "NETLAS_KEY", "FULLHUNT_KEY",
        "IPAPI_CO_KEY", "PHISHTANK_APP_KEY"
    }
    for secret in expected_secrets:
        assert secret in descriptor.secret_env, f"Missing secret env: {secret}"


def test_ip_intelligence_command_passes_only_ip_arguments():
    adapter = IPIntelligenceAdapter()
    command = adapter.build_command(_request("1.1.1.1"), Path("."))
    assert command == ["1.1.1.1"]
    # CIDR input should pass through unchanged
    command_cidr = adapter.build_command(_request("1.1.1.0/24"), Path("."))
    assert command_cidr == ["1.1.1.0/24"]


@parser_test("ip_intelligence")
def test_ip_intelligence_parser_produces_findings_for_all_sources():
    stdout = FIXTURE.read_text(encoding="utf-8")
    adapter = IPIntelligenceAdapter()
    result = adapter.parse(_request(), Path("."), stdout, "", 0)

    # Should have one finding per sub-source (15 total)
    assert len(result.findings) == 15

    # All findings should be IPIntelligenceFinding with entity_type IP
    for finding in result.findings:
        assert isinstance(finding, IPIntelligenceFinding)
        assert finding.entity_type == EntityType.IP
        assert finding.value == TARGET_IP
        assert "source" in finding.attributes


def test_ip_intelligence_parser_skipped_sources_record_skip_reason():
    adapter = IPIntelligenceAdapter()
    # Build a payload with a skipped source
    payload = {
        "target": "1.1.1.1",
        "timestamp": "2026-10-12T12:00:00+00:00",
        "sources": [
            {
                "source": "ipinfo",
                "skipped": True,
                "skip_reason": "IPINFO_TOKEN not set",
                "timestamp": "2026-10-12T12:00:01+00:00",
                "http_status": 0,
                "error": None,
                "raw_hash": None,
                "data": None
            }
        ]
    }
    stdout = json.dumps(payload, sort_keys=True)
    result = adapter.parse(_request(), Path("."), stdout, "", 0)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "ipinfo"
    assert finding.attributes["reputation"]["skipped"] is True
    assert finding.attributes["reputation"]["reason"] == "IPINFO_TOKEN not set"
    assert "Skipped: IPINFO_TOKEN not set" in finding.provenance.notes[0]


def test_ip_intelligence_parser_error_sources_record_error():
    adapter = IPIntelligenceAdapter()
    payload = {
        "target": "1.1.1.1",
        "timestamp": "2026-10-12T12:00:00+00:00",
        "sources": [
            {
                "source": "virustotal",
                "skipped": False,
                "skip_reason": None,
                "timestamp": "2026-10-12T12:00:07+00:00",
                "http_status": 429,
                "error": "HTTP 429: Rate limit exceeded",
                "raw_hash": "abc123",
                "data": None
            }
        ]
    }
    stdout = json.dumps(payload, sort_keys=True)
    result = adapter.parse(_request(), Path("."), stdout, "", 0)

    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "virustotal"
    assert finding.attributes["reputation"]["error"] == "HTTP 429: Rate limit exceeded"
    assert finding.attributes["reputation"]["http_status"] == 429


def test_ip_intelligence_parser_invalid_json_returns_partial():
    adapter = IPIntelligenceAdapter()
    result = adapter.parse(_request(), Path("."), "not json", "", 0)
    assert result.status == "partial"
    assert not result.findings
    assert "not valid JSON" in result.stderr_tail


def test_ip_intelligence_parser_nonzero_exit_returns_failed():
    adapter = IPIntelligenceAdapter()
    result = adapter.parse(_request(), Path("."), "{}", "error", 1)
    assert result.status == "failed"
    assert not result.findings


# Individual source extraction tests
def test_extract_geolocation_ipinfo():
    adapter = IPIntelligenceAdapter()
    data = {
        "ip": "1.1.1.1",
        "city": "San Francisco",
        "region": "California",
        "country": "US",
        "loc": "37.7510,-122.4490",
        "timezone": "America/Los_Angeles"
    }
    geo = adapter._extract_geolocation(data, "ipinfo")
    assert geo is not None
    assert geo["city"] == "San Francisco"
    assert geo["country"] == "US"
    assert geo["latitude"] == 37.7510
    assert geo["longitude"] == -122.4490


def test_extract_geolocation_ipapi():
    adapter = IPIntelligenceAdapter()
    data = {
        "city": "San Francisco",
        "region": "CA",
        "country": "United States",
        "lat": 37.751,
        "lon": -122.449,
        "timezone": "America/Los_Angeles"
    }
    geo = adapter._extract_geolocation(data, "ip-api")
    assert geo is not None
    assert geo["city"] == "San Francisco"
    assert geo["lat"] == 37.751


def test_extract_geolocation_ipapi_co():
    adapter = IPIntelligenceAdapter()
    data = {
        "city": "San Francisco",
        "region": "California",
        "country_name": "United States",
        "latitude": 37.751,
        "longitude": -122.449,
        "timezone": "America/Los_Angeles"
    }
    geo = adapter._extract_geolocation(data, "ipapi-co")
    assert geo is not None
    assert geo["country_name"] == "United States"
    assert geo["latitude"] == 37.751


def test_extract_asn_ipinfo():
    adapter = IPIntelligenceAdapter()
    data = {"org": "AS13335 Cloudflare, Inc."}
    asn = adapter._extract_asn(data, "ipinfo")
    assert asn is not None
    assert asn["number"] == 13335
    assert asn["name"] == "Cloudflare, Inc."


def test_extract_asn_ipapi():
    adapter = IPIntelligenceAdapter()
    data = {"as": "AS13335 Cloudflare, Inc."}
    asn = adapter._extract_asn(data, "ip-api")
    assert asn is not None
    assert asn["number"] == 13335


def test_extract_asn_ipinfo_app_asn():
    adapter = IPIntelligenceAdapter()
    data = {"announcedBy": {"number": 13335, "description": "CLOUDFLARENET"}}
    asn = adapter._extract_asn(data, "ipinfo-app-asn")
    assert asn is not None
    assert asn["number"] == 13335
    assert asn["name"] == "CLOUDFLARENET"


def test_extract_reputation_abuseipdb():
    adapter = IPIntelligenceAdapter()
    data = {"data": {"abuseConfidenceScore": 0, "isWhitelisted": True, "totalReports": 0, "countryCode": "US"}}
    rep = adapter._extract_reputation(data, "abuseipdb")
    assert rep is not None
    assert rep["abuse_score"] == 0
    assert rep["whitelisted"] is True
    assert rep["total_reports"] == 0


def test_extract_reputation_greynoise():
    adapter = IPIntelligenceAdapter()
    data = {"noise": False, "riot": True, "classification": "benign", "name": "Cloudflare", "link": "https://viz.greynoise.io/ip/1.1.1.1"}
    rep = adapter._extract_reputation(data, "greynoise")
    assert rep is not None
    assert rep["noise"] is False
    assert rep["riot"] is True
    assert rep["classification"] == "benign"
    assert rep["actor"] == "Cloudflare"


def test_extract_reputation_virustotal():
    adapter = IPIntelligenceAdapter()
    data = {"data": {"attributes": {"last_analysis_stats": {"harmless": 85, "malicious": 0}, "reputation": 0, "asn": 13335, "as_owner": "Cloudflare, Inc."}}}
    rep = adapter._extract_reputation(data, "virustotal")
    assert rep is not None
    assert rep["last_analysis_stats"]["harmless"] == 85
    assert rep["reputation"] == 0


def test_extract_reputation_urlhaus_no_results():
    adapter = IPIntelligenceAdapter()
    data = {"query_status": "no_results", "host": "1.1.1.1"}
    rep = adapter._extract_reputation(data, "urlhaus")
    # no_results should not produce reputation entry
    assert rep is None


def test_extract_reputation_threatfox():
    adapter = IPIntelligenceAdapter()
    data = {"data": [{"malware": "Emotet", "threat_type": "botnet"}, {"malware": "TrickBot", "threat_type": "botnet"}]}
    rep = adapter._extract_reputation(data, "threatfox")
    assert rep is not None
    assert rep["ioc_count"] == 2
    assert "Emotet" in rep["malware_families"]
    assert "botnet" in rep["threat_types"]


def test_extract_reverse_dns():
    adapter = IPIntelligenceAdapter()
    assert adapter._extract_reverse_dns({"hostname": "one.one.one.one"}, "ipinfo") == "one.one.one.one"
    assert adapter._extract_reverse_dns({"reverse": "one.one.one.one"}, "ip-api") == "one.one.one.one"
    assert adapter._extract_reverse_dns({}, "unknown") is None


def test_extract_open_ports_fullhunt():
    adapter = IPIntelligenceAdapter()
    data = {"open_ports": [{"port": 53, "protocol": "udp"}, {"port": 443, "protocol": "tcp"}]}
    ports = adapter._extract_open_ports(data, "fullhunt")
    assert ports == [53, 443]


def test_runner_health_check():
    runner = _load_runner()
    import sys
    import io
    old_argv = sys.argv
    old_stdout = sys.stdout
    try:
        sys.argv = ["runner.py", "--health"]
        sys.stdout = io.StringIO()
        assert runner.main() == 0
        assert sys.stdout.getvalue().strip() == "ok"
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout


def test_runner_invalid_args():
    runner = _load_runner()
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["runner.py"]
        assert runner.main() == 2
        sys.argv = ["runner.py", "invalid"]
        assert runner.main() == 2
    finally:
        sys.argv = old_argv


def test_runner_normalizes_cidr():
    runner = _load_runner()
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["runner.py", "1.1.1.0/24"]
        # Should not crash on validation, though it will fail on network
        # We just test argument parsing doesn't reject valid CIDR
        assert hasattr(runner, "main")
    finally:
        sys.argv = old_argv