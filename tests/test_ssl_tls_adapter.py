"""Parser + fixture tests for the ssl_tls batch adapter.

No test opens a socket or executes a real TLS tool: the runner's local-tool and
HTTP helpers are replaced with fakes, and every payload used here is synthetic.
"""

import hashlib
import importlib.util
import inspect
import io
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.core.models import (
    AdapterRunRequest,
    EntityType,
    Provenance,
    Seed,
    SeedType,
)
from aletheia.core.project_manifest import load_project_manifest

from aletheia.adapters.ssl_tls import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    SslTlsAdapter,
    SslTlsFinding,
    _extract_detail,
    _extract_details,
    _extract_record_type,
    _extract_severity,
    _extract_subject,
    _extract_target,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PROJECT_MANIFEST.json"
EXPECTED_FIXTURE_PATH = "tests/fixtures/ssl_tls.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = (
    "qualys-ssl-labs",
    "testssl",
    "certgraph",
    "sslscan",
    "tlsx",
    "cipherscan",
)

LOCAL_TOOL_SOURCES = ("testssl", "certgraph", "sslscan", "tlsx", "cipherscan")

# No candidate of this batch is dropped: CipherScan publishes no releases and
# no tags, but the 2026-10-18 re-review (docs/PHASE17_RECHECKS.md #36) resolved
# it to a pinned commit and it is now implemented, so the skip-reason map is
# empty.
SKIP_REASONS: dict[str, str] = {}

# The single documented endpoint the one HTTP sub-source calls, and the official
# documentation URL of every implemented sub-source. The runner resolves each
# from a module constant, so the fixture and the tests can check the exact value
# instead of trusting a literal in a function body.
ENDPOINT_CONSTANTS = {
    "qualys-ssl-labs": "QUALYS_ENDPOINT",
}

DOCS_CONSTANTS = {
    "qualys-ssl-labs": "QUALYS_DOCS",
    "testssl": "TESTSSL_DOCS",
    "certgraph": "CERTGRAPH_DOCS",
    "sslscan": "SSLSCAN_DOCS",
    "tlsx": "TLSX_DOCS",
    "cipherscan": "CIPHERSCAN_DOCS",
}

INVOCATION_CONSTANTS = {
    "qualys-ssl-labs": "QUALYS_INVOCATION",
    "testssl": "TESTSSL_INVOCATION",
    "certgraph": "CERTGRAPH_INVOCATION",
    "sslscan": "SSLSCAN_INVOCATION",
    "tlsx": "TLSX_INVOCATION",
    "cipherscan": "CIPHERSCAN_INVOCATION",
}

# The pinned version of each local tool, and where the pin came from:
#   testssl  -> Debian bookworm package testssl.sh 3.0.8+dfsg-1
#   sslscan  -> Debian bookworm package sslscan 2.0.7-1
#   certgraph-> go install github.com/lanrat/certgraph@v0.1.3 (project releases)
#   tlsx     -> go install github.com/projectdiscovery/tlsx/cmd/tlsx@v1.4.0
#   cipherscan -> pinned commit 30bd23938853d68b51c2ebe4bcc922cc3113c5e2 (the
#                 project has no releases or tags; the script documents no
#                 version switch, so the recorded version is the commit the
#                 image checked out)
PINNED_TOOL_VERSIONS = {
    "testssl": "3.0.8",
    "certgraph": "0.1.3",
    "sslscan": "2.0.7",
    "tlsx": "1.4.0",
    "cipherscan": "30bd23938853d68b51c2ebe4bcc922cc3113c5e2",
}

VERSION_FLAGS = {"--version", "-version"}


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "ssl_tls_runner",
        ROOT / "docker" / "ssl_tls" / "runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_function(module, source: str):
    return getattr(module, "query_" + source.replace("-", "_"))


# -- subject extraction --------------------------------------------------------


def test_extract_subject_qualys_ssl_labs():
    data = {"records": [{"record_id": "93.184.216.34", "detail": "grade A"}]}
    assert _extract_subject(data, "qualys-ssl-labs") == "SSL_LABS:93.184.216.34:grade A"


def test_extract_subject_testssl():
    data = {"records": [{"record_id": "protocols", "detail": "TLS 1.0 is offered"}]}
    assert _extract_subject(data, "testssl") == "TESTSSL:protocols:TLS 1.0 is offered"


def test_extract_subject_certgraph():
    data = {"records": [{"record_id": "domain:example.com", "detail": "domain node at depth 0"}]}
    assert _extract_subject(data, "certgraph") == "CERTGRAPH:domain:example.com:domain node at depth 0"


def test_extract_subject_sslscan():
    data = {"records": [{"record_id": "cipher:AES128-SHA", "detail": "AES128-SHA accepted"}]}
    assert _extract_subject(data, "sslscan") == "SSLSCAN:cipher:AES128-SHA:AES128-SHA accepted"


def test_extract_subject_tlsx():
    data = {"records": [{"record_id": "example.com:443", "detail": "tls13 TLS_AES_256_GCM_SHA384"}]}
    assert _extract_subject(data, "tlsx") == "TLSX:example.com:443:tls13 TLS_AES_256_GCM_SHA384"


def test_extract_subject_cipherscan():
    data = {
        "records": [
            {
                "record_id": "example.com:443/AES256-SHA",
                "detail": "AES256-SHA protocols=TLSv1,TLSv1.1,TLSv1.2 pfs=None trusted=True",
            }
        ]
    }
    assert _extract_subject(data, "cipherscan") == (
        "CIPHERSCAN:example.com:443/AES256-SHA:"
        "AES256-SHA protocols=TLSv1,TLSv1.1,TLSv1.2 pfs=None trusted=True"
    )


def test_extract_subject_without_a_record_falls_back_to_source():
    """A payload with no record never claims a TLS observation."""
    for source in SUPPORTED_SOURCES:
        assert _extract_subject({"records": [], "record_count": 0}, source) == source


# -- record field extraction ---------------------------------------------------


def test_extract_record_type():
    cases = [
        ("qualys-ssl-labs", "qualys_ssl_labs_endpoint_assessment"),
        ("testssl", "testssl_finding"),
        ("certgraph", "certgraph_domain_node"),
        ("sslscan", "sslscan_protocol_or_cipher"),
        ("tlsx", "tlsx_tls_record"),
        ("cipherscan", "cipherscan_cipher_suite"),
        ("unknown-source", None),
    ]
    for source, expected in cases:
        payload = {"records": [{"record_id": "x", "detail": "y"}]}
        result = _extract_record_type(payload, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


def test_extract_record_type_without_a_record_is_none():
    for source in SUPPORTED_SOURCES:
        assert _extract_record_type({"records": []}, source) is None


def test_extract_record_fields_from_the_tlsx_payload():
    data = {
        "query": "example.com",
        "records": [
            {
                "record_id": "example.com:443",
                "detail": "tls13 TLS_AES_256_GCM_SHA384",
                "severity": "info",
                "tls_version": "tls13",
            }
        ],
    }
    assert _extract_detail(data, "tlsx") == "tls13 TLS_AES_256_GCM_SHA384"
    assert _extract_severity(data, "tlsx") == "info"
    assert _extract_target(data, "tlsx") == "example.com"


def test_extract_record_fields_without_a_record_are_none():
    for source in SUPPORTED_SOURCES:
        empty = {"records": [], "record_count": 0}
        assert _extract_detail(empty, source) is None
        assert _extract_severity(empty, source) is None
        assert _extract_target(empty, source) is None


# -- details extraction --------------------------------------------------------


def test_extract_details_qualys_ssl_labs():
    data = {
        "endpoint": "https://api.ssllabs.com/api/v4/analyze",
        "api_documentation": "https://github.com/ssllabs/ssllabs-scan/blob/master/ssllabs-api-docs-v4.md",
        "record_count": 1,
        "truncated": False,
        "assessment_status": "READY",
        "tool": "api.ssllabs.com",
        "tool_version": "2.4.1",
        "records": [
            {
                "record_id": "93.184.216.34",
                "detail": "grade A",
                "severity": "ok",
                "status_message": "Ready",
                "server_name": "example.com",
                "grade": "A",
            }
        ],
    }
    result = _extract_details(data, "qualys-ssl-labs")
    assert result["assessment_status"] == "READY"
    assert result["grade"] == "A"
    assert result["status_message"] == "Ready"
    assert result["server_name"] == "example.com"
    assert result["record_id"] == "93.184.216.34"
    assert result["endpoint"] == "https://api.ssllabs.com/api/v4/analyze"


def test_extract_details_testssl():
    data = {
        "record_count": 1,
        "tool": "testssl",
        "tool_version": "3.0.8",
        "records": [
            {
                "record_id": "protocols",
                "detail": "Synthetic finding: TLS 1.0 is offered",
                "severity": "low",
                "ip": "93.184.216.34",
                "port": "443",
            }
        ],
    }
    result = _extract_details(data, "testssl")
    assert result["record_id"] == "protocols"
    assert result["severity"] == "low"
    assert result["tool_version"] == "3.0.8"
    assert result["ip"] == "93.184.216.34"


def test_extract_details_certgraph():
    data = {
        "graph_depth": 1,
        "num_domains": 1,
        "records": [
            {
                "record_id": "domain:example.com",
                "detail": "domain node at depth 0, status Good",
                "severity": "info",
                "depth": "0",
                "status": "Good",
                "root": "true",
            }
        ],
    }
    result = _extract_details(data, "certgraph")
    assert result["graph_depth"] == 1
    assert result["num_domains"] == 1
    assert result["depth"] == "0"
    assert result["status"] == "Good"


def test_extract_details_sslscan():
    data = {
        "records": [
            {
                "record_id": "cipher:ECDHE-RSA-AES256-GCM-SHA384",
                "detail": "ECDHE-RSA-AES256-GCM-SHA384 accepted",
                "severity": "info",
                "cipher": "ECDHE-RSA-AES256-GCM-SHA384",
                "status": "accepted",
                "tls_version": "TLSv1.2",
                "bits": "256",
                "cipher_id": "0xC030",
            }
        ]
    }
    result = _extract_details(data, "sslscan")
    assert result["cipher"] == "ECDHE-RSA-AES256-GCM-SHA384"
    assert result["status"] == "accepted"
    assert result["tls_version"] == "TLSv1.2"
    assert result["bits"] == "256"
    assert result["cipher_id"] == "0xC030"


def test_extract_details_tlsx():
    data = {
        "records": [
            {
                "record_id": "example.com:443",
                "detail": "tls13 TLS_AES_256_GCM_SHA384",
                "severity": "info",
                "tls_version": "tls13",
                "cipher": "TLS_AES_256_GCM_SHA384",
                "subject_cn": "www.example.com",
            }
        ]
    }
    result = _extract_details(data, "tlsx")
    assert result["tls_version"] == "tls13"
    assert result["cipher"] == "TLS_AES_256_GCM_SHA384"
    assert result["subject_cn"] == "www.example.com"


def test_extract_details_cipherscan():
    data = {
        "target": "example.com:443",
        "serverside": "True",
        "renegotiation": "False",
        "configs_tested": 8,
        "pinned_commit": "30bd23938853d68b51c2ebe4bcc922cc3113c5e2",
        "records": [
            {
                "record_id": "example.com:443/ECDHE-RSA-AES256-GCM-SHA384",
                "detail": "ECDHE-RSA-AES256-GCM-SHA384 protocols=TLSv1.2 pfs=ECDH,P-256,256bits trusted=True",
                "severity": "info",
                "protocols": ["TLSv1.2"],
                "pfs": "ECDH,P-256,256bits",
                "curves": ["prime256v1"],
                "curves_ordering": "server",
            }
        ],
    }
    result = _extract_details(data, "cipherscan")
    assert result["protocols"] == ["TLSv1.2"]
    assert result["pfs"] == "ECDH,P-256,256bits"
    assert result["curves"] == ["prime256v1"]
    assert result["curves_ordering"] == "server"
    assert result["serverside"] == "True"
    assert result["renegotiation"] == "False"
    assert result["configs_tested"] == 8
    assert result["pinned_commit"] == "30bd23938853d68b51c2ebe4bcc922cc3113c5e2"


def test_extract_details_without_a_record_is_none():
    for source in SUPPORTED_SOURCES:
        assert _extract_details({"records": []}, source) is None


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = SslTlsFinding(
        subject="SSLSCAN:cipher:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384 accepted",
        source="sslscan",
        record_type="sslscan_protocol_or_cipher",
        detail="ECDHE-RSA-AES256-GCM-SHA384 accepted",
        target="example.com",
        severity="info",
        tool="sslscan",
        tool_version="2.0.7",
        invocation="sslscan [options] [host:port | host]  (XML: --xml=<file>)",
        details={"cipher": "ECDHE-RSA-AES256-GCM-SHA384"},
        raw_evidence={"records": [{"record_id": "cipher:ECDHE-RSA-AES256-GCM-SHA384"}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:sslscan",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from sslscan"],
        ),
    )
    assert finding.entity_type == EntityType.TLS_OBSERVATION
    assert finding.entity_type.value == "tls_observation"
    assert finding.attributes["source"] == "sslscan"
    assert finding.attributes["severity"] == "info"
    assert finding.attributes["target"] == "example.com"
    assert finding.attributes["tool_version"] == "2.0.7"
    assert finding.subject == finding.value
    assert finding.detail == "ECDHE-RSA-AES256-GCM-SHA384 accepted"


# -- fixture -------------------------------------------------------------------


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    runner = _load_runner()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 6
    assert set(sources) == set(SUPPORTED_SUB_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    assert set(UNSUPPORTED_SUB_SOURCES) == set(SKIP_REASONS)
    assert tuple(runner.SUPPORTED_SUB_SOURCES) == tuple(SUPPORTED_SOURCES)
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES

    by_source = {s["source"]: s for s in fixture["sources"]}
    for source in SUPPORTED_SOURCES:
        entry = by_source[source]
        assert entry["skipped"] is False, source
        assert entry["error"] is None, source
        assert entry["data"], source
        # The fixture hash uses the same convention as the runner: sha256 over
        # json.dumps(data, sort_keys=True).
        assert entry["raw_hash"] == hashlib.sha256(
            json.dumps(entry["data"], sort_keys=True).encode()
        ).hexdigest(), source
        # The recorded documentation URL and invocation are the ones the runner
        # actually uses, so a fixture can never point at a document or an
        # invocation the runner does not claim.
        assert entry["data"]["api_documentation"] == getattr(runner, DOCS_CONSTANTS[source]), source
        assert entry["data"]["invocation"] == getattr(runner, INVOCATION_CONSTANTS[source]), source

    # The one HTTP API sub-source records the documented endpoint; the local
    # tools record no endpoint at all.
    assert by_source["qualys-ssl-labs"]["http_status"] == 200
    assert by_source["qualys-ssl-labs"]["data"]["endpoint"] == getattr(
        runner, ENDPOINT_CONSTANTS["qualys-ssl-labs"]
    )
    for source in LOCAL_TOOL_SOURCES:
        assert by_source[source]["http_status"] == 0, source
        assert by_source[source]["data"]["endpoint"] is None, source
        assert by_source[source]["data"]["source_kind"] == "local_tool", source
        # Every local tool records the argv it ran, and the pinned version of
        # the tool that the image installs.
        assert isinstance(by_source[source]["data"]["command"], list), source
        assert by_source[source]["data"]["tool_version"] == PINNED_TOOL_VERSIONS[source], source

    # No sub-source is dropped: every fixture entry above is a real payload and
    # the skip block that used to follow is gone.


def test_fixture_uses_only_synthetic_values():
    """The fixture is synthetic and must not read as captured live output."""
    fixture = load_fixture()
    # example.com is reserved for documentation (RFC 2606).
    assert fixture["input_value"] == "example.com"
    assert fixture["input_type"] == "domain"
    for entry in fixture["sources"]:
        if entry["skipped"]:
            continue
        data = entry["data"]
        assert data["query"] == "example.com", entry["source"]
        assert data["exit_code"] == 0, entry["source"]
        for record in data["records"]:
            assert record["record_id"], entry["source"]
            assert record["detail"], entry["source"]
            assert record["severity"] in {
                "ok", "info", "warn", "low", "medium", "high", "critical"
            }, entry["source"]
        if data["source_kind"] == "local_tool":
            assert data["raw_output_tail"], entry["source"]
            # The four local tools keep a verbatim excerpt of their own stdout
            # as evidence; three of them print human-readable text, tlsx prints
            # JSONL, so only the text tools carry the synthetic marker.
            if entry["source"] in ("testssl", "certgraph", "sslscan"):
                assert "Synthetic" in data["raw_output_tail"], entry["source"]
    # No credential material is recorded anywhere in the fixture.
    serialized = json.dumps(fixture).casefold()
    assert "ssllabs_email" not in serialized
    assert "api_key" not in serialized
    assert "email" not in json.dumps(fixture["sources"][0]["data"]).casefold()


# -- run result parsing --------------------------------------------------------


def _request(value: str = "example.com") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.DOMAIN, value=value), legal_only=True
    )


def _source(source: str, **overrides) -> dict:
    entry = {
        "source": source,
        "skipped": False,
        "skip_reason": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "http_status": 0,
        "error": None,
        "raw_hash": None,
        "data": None,
    }
    entry.update(overrides)
    return entry


def _payload(sources: list[dict]) -> str:
    return json.dumps(
        {
            "input_type": "domain",
            "input_value": "example.com",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
        }
    )


def _assert_provenance_hash_invariant(findings) -> None:
    for finding in findings:
        raw = finding.attributes.get("raw_evidence")
        assert raw, finding.attributes["source"]
        assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
            json.dumps(raw, sort_keys=True).encode()
        ).hexdigest(), finding.attributes["source"]


@parser_test("ssl_tls")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = SslTlsAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 6

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES)

    qualys = by_source["qualys-ssl-labs"]
    assert qualys.value == "SSL_LABS:93.184.216.34:grade A"
    assert qualys.subject == qualys.value
    assert qualys.record_type == "qualys_ssl_labs_endpoint_assessment"
    assert qualys.detail == "grade A"
    assert qualys.attributes["severity"] == "ok"
    assert qualys.attributes["target"] == "example.com"
    assert qualys.attributes["tool"] == "api.ssllabs.com"
    assert qualys.attributes["details"]["grade"] == "A"
    assert qualys.attributes["details"]["status_message"] == "Ready"
    assert qualys.attributes["details"]["assessment_status"] == "READY"

    testssl = by_source["testssl"]
    assert testssl.value == "TESTSSL:protocols:Synthetic finding: TLS 1.0 is offered"
    assert testssl.record_type == "testssl_finding"
    assert testssl.attributes["severity"] == "low"
    assert testssl.attributes["tool_version"] == "3.0.8"

    certgraph = by_source["certgraph"]
    assert certgraph.value.startswith("CERTGRAPH:domain:example.com:")
    assert certgraph.record_type == "certgraph_domain_node"
    assert certgraph.attributes["details"]["num_domains"] == 1
    assert certgraph.attributes["details"]["status"] == "Good"

    sslscan = by_source["sslscan"]
    assert sslscan.value == "SSLSCAN:cipher:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384 accepted"
    assert sslscan.record_type == "sslscan_protocol_or_cipher"
    assert sslscan.attributes["details"]["bits"] == "256"

    tlsx = by_source["tlsx"]
    assert tlsx.value == "TLSX:example.com:443:tls13 TLS_AES_256_GCM_SHA384"
    assert tlsx.record_type == "tlsx_tls_record"
    assert tlsx.attributes["details"]["tls_version"] == "tls13"
    assert tlsx.attributes["details"]["cipher"] == "TLS_AES_256_GCM_SHA384"

    for finding in result.findings:
        assert isinstance(finding, SslTlsFinding)
        assert finding.entity_type == EntityType.TLS_OBSERVATION
        assert finding.provenance.tool == "ssl_tls"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80

    cipherscan = by_source["cipherscan"]
    assert cipherscan.value == (
        "CIPHERSCAN:example.com:443/AES256-SHA:"
        "AES256-SHA protocols=TLSv1,TLSv1.1,TLSv1.2 pfs=None trusted=True"
    )
    assert cipherscan.record_type == "cipherscan_cipher_suite"
    assert cipherscan.attributes["target"] == "example.com"
    assert cipherscan.attributes["tool"] == "cipherscan"
    assert cipherscan.attributes["tool_version"] == PINNED_TOOL_VERSIONS["cipherscan"]
    assert cipherscan.attributes["details"]["protocols"] == ["TLSv1", "TLSv1.1", "TLSv1.2"]
    assert cipherscan.attributes["details"]["trusted"] == "True"
    assert cipherscan.attributes["details"]["serverside"] == "True"
    assert cipherscan.attributes["details"]["pinned_commit"] == PINNED_TOOL_VERSIONS["cipherscan"]

    _assert_provenance_hash_invariant(result.findings)

    # A mixed runner payload must yield a real finding, a skip finding and an
    # error finding, each with the same provenance hash invariant.
    fixture_by_source = {s["source"]: s for s in fixture["sources"]}
    mixed = _payload(
        [
            _source(
                "sslscan",
                data=fixture_by_source["sslscan"]["data"],
                raw_hash=fixture_by_source["sslscan"]["raw_hash"],
            ),
            _source(
                "testssl",
                skipped=True,
                skip_reason="testssl binary not found in the image",
            ),
            _source(
                "qualys-ssl-labs",
                http_status=429,
                error="HTTP 429: Too Many Requests",
            ),
        ]
    )
    mixed_result = adapter.parse(_request(), Path("."), mixed, "", 0)

    assert mixed_result.status == "succeeded"
    assert len(mixed_result.findings) == 3
    mixed_by_source = {f.attributes["source"]: f for f in mixed_result.findings}

    ok_finding = mixed_by_source["sslscan"]
    assert ok_finding.record_type == "sslscan_protocol_or_cipher"

    skipped = mixed_by_source["testssl"]
    assert skipped.value == "testssl:skipped"
    assert skipped.record_type is None
    assert skipped.attributes["details"] == {
        "skipped": True,
        "reason": "testssl binary not found in the image",
    }
    assert "Skipped: testssl binary not found in the image" in skipped.provenance.notes

    errored = mixed_by_source["qualys-ssl-labs"]
    assert errored.value == "qualys-ssl-labs:error"
    assert errored.record_type is None
    assert errored.attributes["details"] == {
        "error": "HTTP 429: Too Many Requests",
        "http_status": 429,
    }
    assert "Error: HTTP 429: Too Many Requests" in errored.provenance.notes

    for finding in mixed_result.findings:
        assert finding.entity_type == EntityType.TLS_OBSERVATION
    _assert_provenance_hash_invariant(mixed_result.findings)


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    reason = "cipherscan binary not found in the image"
    payload = _payload([_source("cipherscan", skipped=True, skip_reason=reason)])

    adapter = SslTlsAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "cipherscan"
    assert finding.value == "cipherscan:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": reason}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
    assert f"Skipped: {reason}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not an observation."""
    payload = _payload(
        [_source("qualys-ssl-labs", http_status=503, error="HTTP 503: Service Unavailable")]
    )

    adapter = SslTlsAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "qualys-ssl-labs"
    assert finding.value == "qualys-ssl-labs:error"
    assert finding.record_type is None
    assert finding.attributes["details"] == {
        "error": "HTTP 503: Service Unavailable",
        "http_status": 503,
    }
    assert "Error: HTTP 503: Service Unavailable" in finding.provenance.notes

    # A sub-source error must not be reported as an observation.
    assert finding.attributes.get("raw_evidence") == {
        "error": "HTTP 503: Service Unavailable",
        "http_status": 503,
    }
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
        json.dumps(finding.attributes["raw_evidence"], sort_keys=True).encode()
    ).hexdigest()


def test_parse_no_match_produces_no_finding():
    """A source with no observation must not be reported as a record."""
    payload = _payload([_source("tlsx", data=None, raw_hash=None)])

    adapter = SslTlsAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = SslTlsAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = SslTlsAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = SslTlsAdapter()
    assert adapter.supports(SeedType.DOMAIN)
    assert adapter.supports(SeedType.IP)
    assert not adapter.supports(SeedType.EMAIL)
    assert not adapter.supports(SeedType.NAME)


def test_adapter_input_types():
    adapter = SslTlsAdapter()
    type_map = {
        SeedType.DOMAIN: "domain",
        SeedType.IP: "ip",
    }
    for seed_type, expected in type_map.items():
        seed_obj = type("Seed", (), {"type": seed_type, "value": "test_val"})()
        req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
        cmd = adapter.build_command(req, None)
        assert cmd[0] == expected, f"{seed_type}: expected {expected}, got {cmd[0]}"
    assert adapter.descriptor.input_types == [SeedType.DOMAIN, SeedType.IP]


def test_adapter_build_command_domain():
    adapter = SslTlsAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.DOMAIN, "value": "example.com"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["domain", "example.com"]


def test_adapter_build_command_ip():
    adapter = SslTlsAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.IP, "value": "93.184.216.34"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["ip", "93.184.216.34"]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "ssl_tls" in registry
    # Derived from PROJECT_MANIFEST.json rather than hardcoded, so adding an adapter does not
    # require editing this file. Set equality is a stronger assertion than a count: it fails if
    # the registry has an adapter the manifest does not declare, or vice versa.
    manifest = load_project_manifest(MANIFEST)
    declared = {
        entry["name"]
        for entry in manifest["tool_inventory"]
        if "Docker" in str(entry.get("invocation", ""))
    }
    assert declared, "expected the manifest to declare at least one Docker-invoked adapter"
    assert set(registry) == declared

    descriptor = registry["ssl_tls"].descriptor
    assert descriptor.name == "ssl_tls"
    assert descriptor.input_types == [SeedType.DOMAIN, SeedType.IP]
    assert descriptor.output_types == [EntityType.TLS_OBSERVATION]
    assert descriptor.docker_image == "aletheia/ssl-tls:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == ["SSLLABS_EMAIL"]
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)
    assert descriptor.upstream.endswith("docker/ssl_tls")


def test_every_candidate_sub_source_is_implemented():
    """No candidate of the batch is dropped any more."""
    assert UNSUPPORTED_SUB_SOURCES == {}
    assert not set(UNSUPPORTED_SUB_SOURCES) & set(SUPPORTED_SUB_SOURCES)
    assert "cipherscan" in SUPPORTED_SOURCES

    runner = _load_runner()
    assert runner.UNSUPPORTED_SUB_SOURCES == {}
    function_source = inspect.getsource(_runner_function(runner, "cipherscan"))
    assert "CIPHERSCAN_PINNED_COMMIT" in function_source
    assert "http://" not in function_source
    assert "https://" not in function_source


# -- docker runner -------------------------------------------------------------


def test_runner_health_check_reports_tools_without_network_or_subprocess(monkeypatch):
    runner = _load_runner()

    def _forbidden(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError("--health must not use the network or start a subprocess")

    monkeypatch.setattr(runner.subprocess, "run", _forbidden)
    monkeypatch.setattr(runner.urllib.request, "urlopen", _forbidden)

    old_argv = sys.argv
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.argv = ["runner.py", "--health"]
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        assert runner.main() == 0
        stdout = sys.stdout.getvalue()
        stderr = sys.stderr.getvalue()
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    # The Docker integration case asserts stdout.strip() == "ok", so the tool
    # inventory must go to stderr.
    assert stdout.strip() == "ok"
    inventory = json.loads(stderr)
    assert inventory["health"] == "ok"
    assert inventory["network_used"] is False
    assert inventory["subprocesses_started"] is False
    assert [entry["source"] for entry in inventory["sub_sources"]] == list(SUPPORTED_SOURCES)
    for entry in inventory["sub_sources"]:
        assert entry["kind"] in {"http_api", "local_tool"}
        assert "usable" in entry
    assert inventory["dropped_sub_sources"] == []


def test_runner_rejects_invalid_arguments():
    runner = _load_runner()
    old_argv = sys.argv
    old_stderr = sys.stderr
    try:
        sys.stderr = io.StringIO()
        sys.argv = ["runner.py"]
        assert runner.main() == 2
        sys.argv = ["runner.py", "invalid_type", "example.com"]
        assert runner.main() == 2
    finally:
        sys.argv = old_argv
        sys.stderr = old_stderr


def test_runner_reports_every_sub_source():
    runner = _load_runner()
    assert tuple(runner.SUPPORTED_SUB_SOURCES) == tuple(SUPPORTED_SOURCES)
    for source in SUPPORTED_SOURCES:
        function = _runner_function(runner, source)
        assert callable(function)
    result = runner.SourceResult("example")
    assert set(result.to_dict()) == {
        "source",
        "skipped",
        "skip_reason",
        "timestamp",
        "http_status",
        "error",
        "raw_hash",
        "data",
    }


def test_runner_has_no_dropped_sub_sources():
    """Every candidate is implemented, so no skip reason is kept."""
    runner = _load_runner()
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES == {}


def test_runner_supported_sources_cite_a_documented_invocation():
    """Every implemented sub-source cites its own documentation and invocation."""
    runner = _load_runner()
    for source in SUPPORTED_SOURCES:
        docs = getattr(runner, DOCS_CONSTANTS[source])
        invocation = getattr(runner, INVOCATION_CONSTANTS[source])
        assert docs.startswith("https://"), source
        assert invocation.strip(), source
        function_source = inspect.getsource(_runner_function(runner, source))
        assert DOCS_CONSTANTS[source] in function_source, source
        assert INVOCATION_CONSTANTS[source] in function_source, source
    assert getattr(runner, ENDPOINT_CONSTANTS["qualys-ssl-labs"]).startswith("https://")
    # Every pinned version and the drop reason are recorded in RATE_LIMITS.md,
    # which is the document the descriptor points at.
    rate_limits = (ROOT / "docker" / "ssl_tls" / "RATE_LIMITS.md").read_text(encoding="utf-8")
    for version in PINNED_TOOL_VERSIONS.values():
        assert version in rate_limits, version
    assert "cipherscan" in rate_limits


def _install_fake_tools(monkeypatch, runner, *, stdout="", stderr="", code=0, version="synthetic version", write=None):
    """Replace local tool discovery and execution. No real tool is run."""
    calls: list[list[str]] = []

    def fake_run(argv, timeout=0):
        calls.append(list(argv))
        if len(argv) > 1 and argv[1] in VERSION_FLAGS:
            return version + "\n", "", 0, None
        if write is not None:
            write(argv)
        return stdout, stderr, code, None

    monkeypatch.setattr(runner, "_find_tool", lambda name: "/fake/bin/" + name)
    monkeypatch.setattr(runner, "_run_tool", fake_run)
    return calls


TESTSSL_JSON = {
    "scanResult": [
        {
            "id": "protocols",
            "ip": "93.184.216.34",
            "port": "443",
            "severity": "LOW",
            "finding": "Synthetic finding: TLS 1.0 is offered",
        },
        {
            "id": "cipherlist",
            "ip": "93.184.216.34",
            "port": "443",
            "severity": "OK",
            "finding": "Synthetic finding: strong cipher list",
        },
    ]
}

SSLSCAN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<document title="SSLScan Results" version="2.0.7">
<ssltest host="example.com" port="443">
<renegotiation supported="1" secure="1" />
<compression supported="0" />
<heartbleed sslversion="TLSv1.2" vulnerable="0" />
<cipher status="accepted" sslversion="TLSv1.2" bits="256" cipher="ECDHE-RSA-AES256-GCM-SHA384" id="0xC030" strength="good" time="3" />
</ssltest>
</document>
"""

CERTGRAPH_JSON = {
    "nodes": [
        {
            "type": "domain",
            "id": "example.com",
            "status": "Good",
            "root": "true",
            "depth": "0",
            "related": "www.example.com",
            "hasDNS": "true",
        },
        {"type": "certificate", "id": "AAAA", "found": "http"},
    ],
    "links": [],
    "depth": 1,
    "numDomains": 1,
    "certgraph": {"version": "0.1.3"},
}

TLSX_JSONL = (
    '{"timestamp":"2026-10-16T09:00:00Z","host":"example.com","ip":"93.184.216.34",'
    '"port":"443","probe_status":true,"tls_version":"tls13",'
    '"cipher":"TLS_AES_256_GCM_SHA384","subject_cn":"www.example.com","sni":"example.com"}\n'
)


def test_runner_invokes_local_tools_with_an_argv_list(monkeypatch):
    """A local tool is always run from an argv list, never a shell string."""
    runner = _load_runner()
    calls = _install_fake_tools(monkeypatch, runner, stdout=TLSX_JSONL)

    result = runner.query_tlsx("example.com")

    assert result.error is None
    assert result.data is not None
    assert len(calls) == 2  # documented version probe, then the assessment
    for argv in calls:
        assert isinstance(argv, list)
        assert all(isinstance(part, str) for part in argv)
    assert calls[0] == ["/fake/bin/tlsx", "-version"]
    assert calls[1] == ["/fake/bin/tlsx", "-u", "example.com", "-json", "-silent", "-duc"]


def test_runner_never_passes_shell_true(monkeypatch):
    runner = _load_runner()
    kwargs_seen = []

    def fake_run(argv, **kwargs):
        kwargs_seen.append(kwargs)
        return type("P", (), {"stdout": TLSX_JSONL, "stderr": "", "returncode": 0})()

    monkeypatch.setattr(runner, "_find_tool", lambda name: "/fake/bin/" + name)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.query_tlsx("example.com")

    assert kwargs_seen
    for kwargs in kwargs_seen:
        assert "shell" not in kwargs


def test_runner_parses_the_testssl_json_shape(monkeypatch):
    runner = _load_runner()

    def write(argv):
        path = argv[argv.index("--jsonfile-pretty") + 1]
        Path(path).write_text(json.dumps(TESTSSL_JSON), encoding="utf-8")

    _install_fake_tools(monkeypatch, runner, stdout="testssl banner\n", write=write)
    result = runner.query_testssl("example.com")

    assert result.error is None
    data = result.data
    assert data["api_source"] == "testssl.sh"
    assert data["source_kind"] == "local_tool"
    assert data["tool_version"] == "synthetic version"
    assert data["record_count"] == 2
    assert data["records"][0]["record_id"] == "protocols"
    assert data["records"][0]["severity"] == "low"
    assert data["records"][0]["detail"] == "Synthetic finding: TLS 1.0 is offered"
    assert data["records"][0]["ip"] == "93.184.216.34"
    assert result.raw_hash == hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def test_runner_parses_the_sslscan_xml_shape(monkeypatch):
    runner = _load_runner()

    def write(argv):
        path = [part for part in argv if part.startswith("--xml=")][0].split("=", 1)[1]
        Path(path).write_text(SSLSCAN_XML, encoding="utf-8")

    _install_fake_tools(monkeypatch, runner, stdout="sslscan banner\n", write=write)
    result = runner.query_sslscan("example.com")

    assert result.error is None
    data = result.data
    record_ids = [record["record_id"] for record in data["records"]]
    assert record_ids == [
        "renegotiation",
        "compression",
        "heartbleed:TLSv1.2",
        "cipher:ECDHE-RSA-AES256-GCM-SHA384",
    ]
    cipher = data["records"][-1]
    assert cipher["status"] == "accepted"
    assert cipher["tls_version"] == "TLSv1.2"
    assert cipher["bits"] == "256"
    assert cipher["cipher_id"] == "0xC030"
    assert data["records"][2]["vulnerable"] == "0"
    assert data["record_count"] == 4


def test_runner_parses_the_certgraph_json_shape(monkeypatch):
    runner = _load_runner()
    calls = _install_fake_tools(monkeypatch, runner, stdout=json.dumps(CERTGRAPH_JSON))
    result = runner.query_certgraph("example.com")

    assert result.error is None
    data = result.data
    assert data["num_domains"] == 1
    assert data["graph_depth"] == 1
    assert data["records"][0]["record_id"] == "domain:example.com"
    assert data["records"][0]["detail"] == "domain node at depth 0, status Good"
    assert data["records"][0]["has_dns"] == "true"
    assert data["records"][1]["record_id"] == "certificate:AAAA"
    # Documented flags only: -json prints the graph as JSON, -depth bounds the
    # breadth-first crawl.
    assert calls[1] == ["/fake/bin/certgraph", "-json", "-depth", "1", "example.com"]


def test_runner_parses_the_tlsx_jsonl_shape(monkeypatch):
    runner = _load_runner()
    _install_fake_tools(monkeypatch, runner, stdout=TLSX_JSONL)
    result = runner.query_tlsx("example.com")

    assert result.error is None
    data = result.data
    assert data["record_count"] == 1
    record = data["records"][0]
    assert record["record_id"] == "example.com:443"
    assert record["detail"] == "tls13 TLS_AES_256_GCM_SHA384"
    assert record["tls_version"] == "tls13"
    assert record["cipher"] == "TLS_AES_256_GCM_SHA384"
    assert record["ip"] == "93.184.216.34"
    assert record["probe_status"] is True
    assert record["sni"] == "example.com"
    assert result.raw_hash == hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def test_runner_reports_a_missing_local_binary_as_an_error(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_find_tool", lambda name: None)
    for source in LOCAL_TOOL_SOURCES:
        result = _runner_function(runner, source)("example.com")
        assert result.error == source + " binary not found in the image", source
        assert result.skipped is False
        assert result.data is None


def test_runner_reports_a_local_tool_failure_as_an_error(monkeypatch):
    runner = _load_runner()
    _install_fake_tools(monkeypatch, runner, stdout="", stderr="boom", code=1)
    for source in LOCAL_TOOL_SOURCES:
        result = _runner_function(runner, source)("example.com")
        assert result.error, source
        assert "1" in result.error, source
        assert result.data is None, source


def test_runner_reports_no_observation_as_an_empty_payload(monkeypatch):
    """A sub-source with nothing to report carries no data, so no finding is emitted."""
    runner = _load_runner()
    _install_fake_tools(monkeypatch, runner, stdout="")
    for source in ("certgraph", "tlsx"):
        result = _runner_function(runner, source)("example.com")
        assert result.data is None, source
        assert result.error is None, source


# -- Qualys SSL Labs API -------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode()
        self.status = status

    def read(self, _limit=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


SSL_LABS_PAYLOAD = {
    "host": "example.com",
    "port": 443,
    "protocol": "HTTP",
    "isPublic": False,
    "status": "READY",
    "engineVersion": "2.4.1",
    "criteriaVersion": "2009f",
    "endpoints": [
        {
            "ipAddress": "93.184.216.34",
            "serverName": "example.com",
            "statusMessage": "Ready",
            "grade": "A",
            "gradeTrustIgnored": "A",
            "hasWarnings": False,
        }
    ],
}


def test_runner_skips_qualys_without_the_configured_credential(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv("SSLLABS_EMAIL", raising=False)

    def _forbidden(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError("an unregistered client must not call the API")

    monkeypatch.setattr(runner.urllib.request, "urlopen", _forbidden)
    result = runner.query_qualys_ssl_labs("example.com")

    assert result.skipped is True
    assert "SSLLABS_EMAIL is not set" in result.skip_reason
    assert result.data is None
    assert result.raw_hash is None


def test_runner_queries_qualys_with_the_documented_email_header(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("SSLLABS_EMAIL", "secret-ssllabs-value@example.org")
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["timeout"] = timeout
        return _FakeResponse(SSL_LABS_PAYLOAD)

    monkeypatch.setattr(runner.urllib.request, "urlopen", fake_urlopen)
    result = runner.query_qualys_ssl_labs("example.com")

    assert result.http_status == 200
    assert result.error is None
    assert captured["url"] == "https://api.ssllabs.com/api/v4/analyze?host=example.com"
    assert captured["headers"].get("Email") == "secret-ssllabs-value@example.org"

    data = result.data
    assert data["assessment_status"] == "READY"
    assert data["records"][0]["record_id"] == "93.184.216.34"
    assert data["records"][0]["detail"] == "grade A"
    assert data["records"][0]["severity"] == "ok"
    assert data["records"][0]["status_message"] == "Ready"
    # The credential is never written into the runner output.
    assert "secret-ssllabs-value" not in json.dumps(result.to_dict())
    assert data["command"] == ["GET", captured["url"]]


def test_runner_reports_an_in_progress_assessment_as_a_status_record(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("SSLLABS_EMAIL", "secret-ssllabs-value@example.org")
    payload = {"host": "example.com", "status": "IN_PROGRESS", "endpoints": []}
    monkeypatch.setattr(
        runner.urllib.request, "urlopen", lambda request, timeout=0: _FakeResponse(payload)
    )
    result = runner.query_qualys_ssl_labs("example.com")

    assert result.error is None
    record = result.data["records"][0]
    assert record["record_id"] == "assessment"
    assert record["detail"] == "assessment status IN_PROGRESS"
    assert record["severity"] == "info"


def test_runner_reports_an_http_error_as_an_error_result(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("SSLLABS_EMAIL", "secret-ssllabs-value@example.org")

    def fake_urlopen(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", None, None)

    monkeypatch.setattr(runner.urllib.request, "urlopen", fake_urlopen)
    result = runner.query_qualys_ssl_labs("example.com")

    assert result.data is None
    assert result.http_status == 429
    assert result.error.startswith("HTTP 429")


def test_runner_never_prints_a_configured_secret(monkeypatch):
    """A configured credential is sent but never echoed in the payload."""
    runner = _load_runner()
    monkeypatch.setenv("SSLLABS_EMAIL", "secret-ssllabs-value@example.org")
    monkeypatch.setattr(
        runner.urllib.request,
        "urlopen",
        lambda request, timeout=0: _FakeResponse({"status": "ERROR", "endpoints": []}),
    )
    result = runner.query_qualys_ssl_labs("example.com")
    assert "secret-" not in json.dumps(result.to_dict())


# -- CipherScan (local tool) ---------------------------------------------------

CIPHERSCAN_JSON = {
    "target": "example.com:443",
    "utctimestamp": "2026-10-16T09:00:00Z",
    "serverside": "True",
    "ciphersuite": [
        {
            "cipher": "AES256-SHA",
            "protocols": ["TLSv1", "TLSv1.1", "TLSv1.2"],
            "pubkey": ["2048"],
            "sigalg": ["sha1WithRSAEncryption"],
            "trusted": "True",
            "ticket_hint": "None",
            "ocsp_stapling": "False",
            "npn": [],
            "pfs": "None",
        },
        {
            "cipher": "ECDHE-RSA-AES256-GCM-SHA384",
            "protocols": ["TLSv1.2"],
            "pubkey": ["2048"],
            "sigalg": ["sha256WithRSAEncryption"],
            "trusted": "True",
            "ticket_hint": "None",
            "ocsp_stapling": "False",
            "npn": [],
            "pfs": "ECDH,P-256,256bits",
            "curves": ["prime256v1"],
            "curves_ordering": "server",
        },
    ],
    "renegotiation": "False",
    "compression": "False",
    "configs": {"Modern": {"tolerant": "True"}},
    "intolerancies": [{"name": "TLS 1.0", "tolerant": "False"}],
}


def test_runner_parses_the_cipherscan_json_shape(monkeypatch):
    runner = _load_runner()
    calls = _install_fake_tools(monkeypatch, runner, stdout=json.dumps(CIPHERSCAN_JSON))
    result = runner.query_cipherscan("example.com")

    assert result.error is None
    data = result.data
    # The scan is the only subprocess: no version probe exists for CipherScan.
    assert calls == [["/fake/bin/cipherscan", "-j", "example.com"]]
    assert data["api_source"] == "CipherScan (openssl s_client wrapper)"
    assert data["source_kind"] == "local_tool"
    assert data["tool_version"] == runner.CIPHERSCAN_PINNED_COMMIT
    assert data["record_count"] == 2
    first = data["records"][0]
    assert first["record_id"] == "example.com:443/AES256-SHA"
    assert first["detail"] == "AES256-SHA protocols=TLSv1,TLSv1.1,TLSv1.2 pfs=None trusted=True"
    assert first["protocols"] == ["TLSv1", "TLSv1.1", "TLSv1.2"]
    assert first["trusted"] == "True"
    second = data["records"][1]
    assert second["curves"] == ["prime256v1"]
    assert second["curves_ordering"] == "server"
    assert data["target"] == "example.com:443"
    assert data["renegotiation"] == "False"
    assert data["compression"] == "False"
    assert data["configs_tested"] == 1
    assert data["intolerancies_present"] is True
    assert data["pinned_commit"] == runner.CIPHERSCAN_PINNED_COMMIT
    assert result.raw_hash == hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def test_runner_cipherscan_rejects_output_that_is_not_json(monkeypatch):
    runner = _load_runner()
    _install_fake_tools(monkeypatch, runner, stdout="not json at all")
    result = runner.query_cipherscan("example.com")
    assert result.data is None
    assert result.error == "cipherscan did not print JSON output"


def test_runner_cipherscan_with_no_cipher_suites_is_an_empty_payload(monkeypatch):
    runner = _load_runner()
    _install_fake_tools(
        monkeypatch, runner, stdout=json.dumps({"target": "example.com:443", "ciphersuite": []})
    )
    result = runner.query_cipherscan("example.com")
    assert result.data is None
    assert result.error is None


def test_runner_cipherscan_reports_a_tool_failure(monkeypatch):
    runner = _load_runner()
    _install_fake_tools(monkeypatch, runner, stdout="", stderr="boom", code=1)
    result = runner.query_cipherscan("example.com")
    assert result.data is None
    assert result.error == "cipherscan exited with code 1: boom"


def test_runner_cipherscan_selftest_reports_a_missing_binary(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_find_tool", lambda name: None)
    report = runner._cipherscan_selftest()
    assert report["cipherscan_selftest"] == "failed"
    assert "binary not found" in report["error"]
    assert report["pinned_commit"] == runner.CIPHERSCAN_PINNED_COMMIT


def test_runner_selftest_mode_runs_the_cipherscan_selftest(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_cipherscan_selftest",
        lambda: {
            "cipherscan_selftest": "ok",
            "pinned_commit": runner.CIPHERSCAN_PINNED_COMMIT,
            "ciphers_found": 2,
        },
    )
    old_argv = sys.argv
    old_stdout = sys.stdout
    try:
        sys.argv = ["runner.py", "--selftest-cipherscan"]
        sys.stdout = io.StringIO()
        assert runner.main() == 0
        report = json.loads(sys.stdout.getvalue())
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
    assert report["cipherscan_selftest"] == "ok"
    assert report["pinned_commit"] == runner.CIPHERSCAN_PINNED_COMMIT


def test_runner_selftest_mode_fails_when_the_cipherscan_selftest_fails(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_cipherscan_selftest",
        lambda: {
            "cipherscan_selftest": "failed",
            "pinned_commit": runner.CIPHERSCAN_PINNED_COMMIT,
            "error": "boom",
        },
    )
    old_argv = sys.argv
    old_stdout = sys.stdout
    try:
        sys.argv = ["runner.py", "--selftest-cipherscan"]
        sys.stdout = io.StringIO()
        assert runner.main() == 1
        report = json.loads(sys.stdout.getvalue())
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
    assert report["error"] == "boom"
