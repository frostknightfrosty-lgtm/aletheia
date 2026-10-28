"""Parser + fixture tests for the email_auth batch adapter."""

import hashlib
import importlib.util
import inspect
import io
import json
import sys
import types
import urllib.parse
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

from aletheia.adapters.email_auth import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    EmailAuthAdapter,
    EmailAuthFinding,
    _extract_details,
    _extract_domain,
    _extract_grade,
    _extract_record_type,
    _extract_score,
    _extract_subject,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIXTURE_PATH = "tests/fixtures/email_auth.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = (
    "scan-mx",
    "checkdmarc",
)

# A synthetic domain placeholder, not a real registered domain's live report.
FIXTURE_INPUT_VALUE = "example.com"


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "email_auth_runner",
        ROOT / "docker" / "email_auth" / "runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_function(module, source: str):
    return getattr(module, "query_" + source.replace("-", "_"))


def _expected_scan_mx_endpoint(runner, value: str) -> str:
    return runner.SCAN_MX_CHECK_URL + "?" + urllib.parse.urlencode({"domain": value})


# -- subject extraction --------------------------------------------------------


def test_extract_subject_scan_mx():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "report"}]}
    assert _extract_subject(data, "scan-mx") == "SCANMX:" + FIXTURE_INPUT_VALUE


def test_extract_subject_checkdmarc():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "result"}]}
    assert _extract_subject(data, "checkdmarc") == "CHECKDMARC:" + FIXTURE_INPUT_VALUE


def test_extract_subject_without_a_record_falls_back_to_source():
    """A payload with no record never claims a record subject."""
    for source in SUPPORTED_SOURCES:
        assert _extract_subject({"records": [], "record_count": 0}, source) == source


# -- record type, domain and grade ---------------------------------------------


def test_extract_record_type():
    cases = [
        ("scan-mx", "scan_mx_email_authentication_report"),
        ("checkdmarc", "checkdmarc_email_authentication_record"),
        ("unknown-source", None),
    ]
    for source, expected in cases:
        record = None if source == "unknown-source" else {"record_id": "x"}
        data = {"records": [record] if record else []}
        result = _extract_record_type(data, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


def test_extract_domain_prefers_the_query():
    assert _extract_domain({"query": FIXTURE_INPUT_VALUE}, "scan-mx") == FIXTURE_INPUT_VALUE
    assert _extract_domain({"records": [{"record_id": "x"}]}, "scan-mx") == "x"
    assert _extract_domain({"records": []}, "scan-mx") is None


def test_extract_grade_and_score():
    data = {"records": [{"record_id": "x", "grade": "A", "score": 95}]}
    assert _extract_grade(data, "scan-mx") == "A"
    assert _extract_score(data, "scan-mx") == 95.0
    # A boolean score is never treated as a numeric grade.
    assert _extract_score({"records": [{"score": True}]}, "scan-mx") is None
    # checkdmarc carries no numeric grade.
    assert _extract_grade({"records": [{"record_id": "x"}]}, "checkdmarc") is None
    assert _extract_score({"records": [{"record_id": "x"}]}, "checkdmarc") is None


# -- details extraction --------------------------------------------------------


def test_extract_details_scan_mx():
    data = {
        "api_source": "scan.mx email authentication and deliverability API",
        "api_documentation": "https://api.scan.mx/",
        "endpoint": "https://api.scan.mx/v1/check?domain=" + FIXTURE_INPUT_VALUE,
        "query": FIXTURE_INPUT_VALUE,
        "record_count": 1,
        "check_count": 1,
        "records": [
            {
                "record_id": FIXTURE_INPUT_VALUE,
                "detail": "report",
                "grade": "A",
                "score": 95,
                "provider": "Synthetic Mail Provider",
                "email_configured": True,
                "smtp_status": "n/a",
                "sections": {"mx": {"score": 100, "grade": "A"}},
                "checks": [{"id": "mx.presence", "status": "pass"}],
            }
        ],
    }
    result = _extract_details(data, "scan-mx")
    assert result["grade"] == "A"
    assert result["score"] == 95
    assert result["provider"] == "Synthetic Mail Provider"
    assert result["email_configured"] is True
    assert result["smtp_status"] == "n/a"
    assert result["sections"]["mx"]["grade"] == "A"
    assert result["check_count"] == 1
    assert result["record_count"] == 1
    assert result["truncated"] is False


def test_extract_details_checkdmarc():
    data = {
        "api_source": "checkdmarc (Python library, DNS records checked directly)",
        "api_documentation": "https://domainaware.github.io/checkdmarc/api.html",
        "module": "checkdmarc",
        "query": FIXTURE_INPUT_VALUE,
        "records": [
            {
                "record_id": FIXTURE_INPUT_VALUE,
                "detail": "result",
                "domain": FIXTURE_INPUT_VALUE,
                "base_domain": FIXTURE_INPUT_VALUE,
                "dnssec": False,
                "mx": {"hosts": [{"hostname": "mx.example.com"}], "warnings": []},
                "spf": {"record": "v=spf1 -all", "valid": True},
                "dmarc": {"record": "v=DMARC1; p=reject;", "valid": True},
            }
        ],
    }
    result = _extract_details(data, "checkdmarc")
    assert result["module"] == "checkdmarc"
    assert result["mx"]["hosts"][0]["hostname"] == "mx.example.com"
    assert result["spf"]["record"] == "v=spf1 -all"
    assert result["dmarc"]["record"] == "v=DMARC1; p=reject;"
    assert result["dnssec"] is False


def test_extract_details_without_a_record_is_none():
    assert _extract_details({"records": []}, "scan-mx") is None


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = EmailAuthFinding(
        subject="SCANMX:" + FIXTURE_INPUT_VALUE,
        source="scan-mx",
        record_type="scan_mx_email_authentication_report",
        domain=FIXTURE_INPUT_VALUE,
        grade="A",
        score=95.0,
        date="2026-10-16",
        details={"provider": "Synthetic Mail Provider"},
        raw_evidence={"records": [{"record_id": FIXTURE_INPUT_VALUE}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:scan-mx",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from scan-mx"],
        ),
    )
    assert finding.entity_type == EntityType.EMAIL_AUTH_RECORD
    assert finding.entity_type.value == "email_auth_record"
    assert finding.attributes["source"] == "scan-mx"
    assert finding.attributes["grade"] == "A"
    assert finding.attributes["score"] == 95.0
    assert finding.subject == "SCANMX:" + FIXTURE_INPUT_VALUE
    assert finding.domain == FIXTURE_INPUT_VALUE
    assert finding.grade == "A"
    assert finding.score == 95.0


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    runner = _load_runner()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 2
    assert set(sources) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    assert tuple(runner.SUPPORTED_SUB_SOURCES) == tuple(SUPPORTED_SOURCES)
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES

    by_source = {s["source"]: s for s in fixture["sources"]}
    for source in SUPPORTED_SOURCES:
        entry = by_source[source]
        assert entry["skipped"] is False, source
        assert entry["error"] is None, source
        assert entry["http_status"] == 200, source
        assert entry["data"], source
        # The fixture hash uses the same convention as the runner: sha256 over
        # json.dumps(data, sort_keys=True).
        assert entry["raw_hash"] == hashlib.sha256(
            json.dumps(entry["data"], sort_keys=True).encode()
        ).hexdigest(), source
        assert entry["data"]["query"] == FIXTURE_INPUT_VALUE, source

    # The recorded scan.mx endpoint is the one the runner actually requests, so a
    # fixture can never point at an endpoint the runner does not use.
    assert by_source["scan-mx"]["data"]["endpoint"] == _expected_scan_mx_endpoint(
        runner, FIXTURE_INPUT_VALUE
    )
    assert by_source["scan-mx"]["data"]["api_documentation"] == runner.SCAN_MX_DOCS
    assert by_source["scan-mx"]["data"]["invocation"] == runner.SCAN_MX_INVOCATION
    # The checkdmarc record cites the documented module and entry point.
    assert by_source["checkdmarc"]["data"]["module"] == runner.CHECKDMARC_MODULE
    assert by_source["checkdmarc"]["data"]["entry_point"] == runner.CHECKDMARC_ENTRY_POINT
    assert by_source["checkdmarc"]["data"]["api_documentation"] == runner.CHECKDMARC_DOCS
    assert by_source["checkdmarc"]["data"]["invocation"] == runner.CHECKDMARC_INVOCATION


def test_fixture_has_no_dropped_candidate():
    """Both candidates were verified, so nothing is reported as a dropped skip."""
    fixture = load_fixture()
    assert UNSUPPORTED_SUB_SOURCES == {}
    assert all(entry["skipped"] is False for entry in fixture["sources"])


def test_fixture_uses_only_synthetic_values():
    """The fixture is synthetic and must not read as captured live output."""
    fixture = load_fixture()
    assert fixture["input_type"] == "domain"
    assert fixture["input_value"] == FIXTURE_INPUT_VALUE
    blob = json.dumps(fixture)
    assert "Synthetic" in blob
    for entry in fixture["sources"]:
        assert entry["data"]["query"] == fixture["input_value"]


# -- run result parsing --------------------------------------------------------


def _request(value: str = FIXTURE_INPUT_VALUE) -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=SeedType.DOMAIN, value=value),
        legal_only=True,
    )


def _source(source: str, **overrides) -> dict:
    entry = {
        "source": source,
        "skipped": False,
        "skip_reason": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "http_status": 200,
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
            "input_value": FIXTURE_INPUT_VALUE,
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


@parser_test("email_auth")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = EmailAuthAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 2

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)

    scan_mx = by_source["scan-mx"]
    assert scan_mx.value == "SCANMX:" + FIXTURE_INPUT_VALUE
    assert scan_mx.subject == "SCANMX:" + FIXTURE_INPUT_VALUE
    assert scan_mx.record_type == "scan_mx_email_authentication_report"
    assert scan_mx.domain == FIXTURE_INPUT_VALUE
    assert scan_mx.grade == "A"
    assert scan_mx.score == 95.0
    assert scan_mx.attributes["details"]["grade"] == "A"
    assert scan_mx.attributes["details"]["provider"] == "Synthetic Mail Provider"
    assert scan_mx.attributes["details"]["sections"]["mx"]["grade"] == "A"
    assert scan_mx.attributes["date"] == fixture["sources"][0]["timestamp"][:10]

    checkdmarc = by_source["checkdmarc"]
    assert checkdmarc.value == "CHECKDMARC:" + FIXTURE_INPUT_VALUE
    assert checkdmarc.subject == "CHECKDMARC:" + FIXTURE_INPUT_VALUE
    assert checkdmarc.record_type == "checkdmarc_email_authentication_record"
    assert checkdmarc.domain == FIXTURE_INPUT_VALUE
    assert checkdmarc.grade is None
    assert checkdmarc.score is None
    assert checkdmarc.attributes["details"]["module"] == "checkdmarc"
    assert checkdmarc.attributes["details"]["mx"]["hosts"][0]["hostname"] == "mx.example.com"
    assert checkdmarc.attributes["details"]["spf"]["record"] == "v=spf1 -all"
    assert checkdmarc.attributes["details"]["dmarc"]["record"] == "v=DMARC1; p=reject;"

    for finding in result.findings:
        assert isinstance(finding, EmailAuthFinding)
        assert finding.entity_type == EntityType.EMAIL_AUTH_RECORD
        assert finding.provenance.tool == "email_auth"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80

    _assert_provenance_hash_invariant(result.findings)

    # A mixed runner payload must yield a real finding, a skip finding and an
    # error finding, each with the same provenance hash invariant.
    mixed = _payload(
        [
            _source(
                "scan-mx",
                data=fixture["sources"][0]["data"],
                raw_hash=fixture["sources"][0]["raw_hash"],
            ),
            _source(
                "checkdmarc",
                skipped=True,
                skip_reason="checkdmarc is not importable in this image",
                http_status=0,
            ),
            _source(
                "scan-mx",
                http_status=429,
                error="HTTP 429: Too Many Requests",
            ),
        ]
    )
    mixed_result = adapter.parse(_request(), Path("."), mixed, "", 0)

    assert mixed_result.status == "succeeded"
    assert len(mixed_result.findings) == 3

    # Two entries name scan-mx, so select findings by their subject value.
    ok_finding = next(
        f for f in mixed_result.findings if f.value == "SCANMX:" + FIXTURE_INPUT_VALUE
    )
    assert ok_finding.record_type == "scan_mx_email_authentication_report"

    skipped_finding = next(f for f in mixed_result.findings if f.value == "checkdmarc:skipped")
    assert skipped_finding.record_type is None
    assert skipped_finding.attributes["details"] == {
        "skipped": True,
        "reason": "checkdmarc is not importable in this image",
    }
    assert "Skipped: checkdmarc is not importable in this image" in skipped_finding.provenance.notes

    error_finding = next(f for f in mixed_result.findings if f.value == "scan-mx:error")
    assert error_finding.record_type is None
    assert error_finding.attributes["details"] == {
        "error": "HTTP 429: Too Many Requests",
        "http_status": 429,
    }
    assert "Error: HTTP 429: Too Many Requests" in error_finding.provenance.notes

    for finding in mixed_result.findings:
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.EMAIL_AUTH_RECORD)
    _assert_provenance_hash_invariant(mixed_result.findings)


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    reason = "checkdmarc is not importable in this image"
    payload = _payload([_source("checkdmarc", skipped=True, skip_reason=reason, http_status=0)])

    adapter = EmailAuthAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "checkdmarc"
    assert finding.value == "checkdmarc:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": reason}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
    assert f"Skipped: {reason}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not a record."""
    payload = _payload(
        [_source("scan-mx", http_status=429, error="HTTP 429: Too Many Requests")]
    )

    adapter = EmailAuthAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "scan-mx"
    assert finding.value == "scan-mx:error"
    assert finding.attributes["details"] == {
        "error": "HTTP 429: Too Many Requests",
        "http_status": 429,
    }
    assert "Error: HTTP 429: Too Many Requests" in finding.provenance.notes

    # A sub-source error must not be reported as a successful record.
    assert finding.record_type is None
    assert finding.attributes.get("raw_evidence") == {
        "error": "HTTP 429: Too Many Requests",
        "http_status": 429,
    }
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
        json.dumps(finding.attributes["raw_evidence"], sort_keys=True).encode()
    ).hexdigest()


def test_parse_no_match_produces_no_finding():
    """A source with no record must not be reported as a finding."""
    payload = _payload([_source("scan-mx", data=None, raw_hash=None)])

    adapter = EmailAuthAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = EmailAuthAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = EmailAuthAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = EmailAuthAdapter()
    assert adapter.supports(SeedType.DOMAIN)
    assert not adapter.supports(SeedType.NAME)
    assert not adapter.supports(SeedType.EMAIL)
    assert not adapter.supports(SeedType.CRYPTO_ADDRESS)


def test_adapter_build_command_domain():
    adapter = EmailAuthAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.DOMAIN, "value": "example.com"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["domain", "example.com"]
    assert adapter.descriptor.input_types == [SeedType.DOMAIN]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "email_auth" in registry
    # Derived from PROJECT_MANIFEST.json rather than hardcoded, so adding an adapter does not
    # require editing this file. Set equality is stronger than a count: it fails if the registry
    # has an adapter the manifest does not declare, or vice versa.
    manifest = load_project_manifest(ROOT / "PROJECT_MANIFEST.json")
    declared = {
        entry["name"]
        for entry in manifest["tool_inventory"]
        if "Docker" in str(entry.get("invocation", ""))
    }
    assert declared, "expected the manifest to declare at least one Docker-invoked adapter"
    assert set(registry) == declared

    descriptor = registry["email_auth"].descriptor
    assert descriptor.name == "email_auth"
    assert descriptor.input_types == [SeedType.DOMAIN]
    assert descriptor.output_types == [EntityType.EMAIL_AUTH_RECORD]
    assert descriptor.docker_image == "aletheia/email-auth:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == []
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)
    assert descriptor.upstream.endswith("docker/email_auth")


# -- docker runner -------------------------------------------------------------


def test_runner_health_check():
    runner = _load_runner()
    old_argv = sys.argv
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.argv = ["runner.py", "--health"]
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        assert runner.main() == 0
        assert sys.stdout.getvalue().strip() == "ok"
        inventory = json.loads(sys.stderr.getvalue().strip())
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    assert inventory["health"] == "ok"
    assert inventory["network_used"] is False
    kinds = {entry["source"]: entry["kind"] for entry in inventory["sub_sources"]}
    assert kinds["scan-mx"] == "http_api"
    assert kinds["checkdmarc"] == "library"
    assert inventory["dropped_sub_sources"] == []
    by_source = {entry["source"]: entry for entry in inventory["sub_sources"]}
    assert by_source["scan-mx"]["endpoint"] == runner.SCAN_MX_CHECK_URL
    assert by_source["scan-mx"]["usable"] is True
    assert by_source["checkdmarc"]["module"] == runner.CHECKDMARC_MODULE
    assert by_source["checkdmarc"]["usable"] == runner._checkdmarc_available()


def test_runner_rejects_invalid_arguments():
    runner = _load_runner()
    old_argv = sys.argv
    old_stderr = sys.stderr
    try:
        sys.stderr = io.StringIO()
        sys.argv = ["runner.py"]
        assert runner.main() == 2
        sys.argv = ["runner.py", "invalid_type", FIXTURE_INPUT_VALUE]
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


def test_runner_defines_no_endpoint_for_dropped_source():
    """A dropped candidate is an auditable skip with no URL, never a guessed call."""
    runner = _load_runner()
    for source, reason in runner.UNSUPPORTED_SUB_SOURCES.items():
        assert isinstance(reason, str) and reason.strip()
        function_source = inspect.getsource(_runner_function(runner, source))
        assert "http://" not in function_source
        assert "https://" not in function_source


def test_runner_supported_sources_cite_a_documented_endpoint():
    """Every implemented sub-source cites a documented contract."""
    runner = _load_runner()
    assert runner.SCAN_MX_CHECK_URL.startswith("https://")
    function_source = inspect.getsource(runner.query_scan_mx)
    assert "SCAN_MX_CHECK_URL" in function_source
    assert runner.CHECKDMARC_ENTRY_POINT == "checkdmarc.check_domains"
    checkdmarc_source = inspect.getsource(runner.query_checkdmarc)
    assert "check_domains" in checkdmarc_source
    assert "CHECKDMARC_ENTRY_POINT" in checkdmarc_source


def test_runner_skips_a_non_fqdn_seed(monkeypatch):
    """A value that is not an FQDN is never sent to either sub-source."""
    runner = _load_runner()
    assert runner._domain("example.com") == "example.com"
    assert runner._domain("Example.COM") == "example.com"
    assert runner._domain("not a domain") == ""
    assert runner._domain("localhost") == ""
    for source in SUPPORTED_SOURCES:
        result = _runner_function(runner, source)("not a domain")
        assert result.skipped is True, source
        assert result.data is None, source


def test_runner_parses_the_documented_scan_mx_shape(monkeypatch):
    runner = _load_runner()
    payload = {
        "domain": FIXTURE_INPUT_VALUE,
        "grade": "A",
        "score": 95,
        "provider": "Synthetic Mail Provider",
        "email_configured": True,
        "smtp_status": "n/a",
        "sections": {"mx": {"score": 100, "grade": "A"}},
        "checks": [{"id": "mx.presence", "section": "mx", "status": "pass"}],
        "permalink": "https://scan.mx/" + FIXTURE_INPUT_VALUE,
        "expires_at": 1778912400,
    }
    monkeypatch.setattr(runner, "_fetch_json", lambda *a, **k: (payload, 200, None))
    result = runner.query_scan_mx(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert result.http_status == 200
    assert result.data["records"][0]["grade"] == "A"
    assert result.data["records"][0]["score"] == 95
    assert result.data["records"][0]["provider"] == "Synthetic Mail Provider"
    assert result.data["check_count"] == 1
    assert result.data["endpoint"] == _expected_scan_mx_endpoint(runner, FIXTURE_INPUT_VALUE)


def test_runner_parses_the_documented_checkdmarc_shape(monkeypatch):
    """The checkdmarc path is monkeypatched: no import, no DNS, no network."""
    runner = _load_runner()
    fake_result = {
        "domain": FIXTURE_INPUT_VALUE,
        "base_domain": FIXTURE_INPUT_VALUE,
        "dnssec": False,
        "mx": {"hosts": [{"hostname": "mx.example.com", "preference": 10}], "warnings": []},
        "spf": {"record": "v=spf1 -all", "valid": True},
        "dmarc": {"record": "v=DMARC1; p=reject;", "valid": True},
    }
    fake_module = types.SimpleNamespace(check_domains=lambda domains: dict(fake_result))
    monkeypatch.setattr(runner, "_import_checkdmarc", lambda: fake_module)

    result = runner.query_checkdmarc(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert result.skipped is False
    record = result.data["records"][0]
    assert record["record_id"] == FIXTURE_INPUT_VALUE
    assert record["mx"]["hosts"][0]["hostname"] == "mx.example.com"
    assert record["spf"]["record"] == "v=spf1 -all"
    assert record["dmarc"]["record"] == "v=DMARC1; p=reject;"
    assert result.data["module"] == "checkdmarc"
    assert result.data["record_count"] == 1


def test_runner_reports_a_missing_checkdmarc_import_as_a_skip(monkeypatch):
    """A missing library is a documented skip, never a crash."""
    runner = _load_runner()

    def boom():
        raise ModuleNotFoundError("No module named 'checkdmarc'")

    monkeypatch.setattr(runner, "_import_checkdmarc", boom)
    result = runner.query_checkdmarc(FIXTURE_INPUT_VALUE)

    assert result.skipped is True
    assert result.data is None
    assert "checkdmarc" in result.skip_reason
    assert runner.CHECKDMARC_VERSION in result.skip_reason


def test_runner_records_an_http_error_without_leaking_anything(monkeypatch):
    """A failing scan.mx request is recorded as an error with no data."""
    runner = _load_runner()
    monkeypatch.setattr(
        runner, "_fetch_json", lambda *a, **k: (None, 429, "HTTP 429: Too Many Requests")
    )
    result = runner.query_scan_mx(FIXTURE_INPUT_VALUE)
    assert result.error == "HTTP 429: Too Many Requests"
    assert result.data is None
