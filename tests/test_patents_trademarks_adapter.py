"""Parser + fixture tests for the patents_trademarks batch adapter."""

import hashlib
import importlib.util
import inspect
import io
import json
import sys
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

from aletheia.adapters.patents_trademarks import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    PatentsTrademarksAdapter,
    PatentsTrademarksFinding,
    _extract_details,
    _extract_identifier,
    _extract_ip_kind,
    _extract_jurisdiction,
    _extract_record_type,
    _extract_subject,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIXTURE_PATH = "tests/fixtures/patents_trademarks.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = (
    "uspto-open-data",
    "uspto-patent-assignment",
    "uspto-tsdr",
    "epo-ops",
)

# A synthetic numeric placeholder, not a real application or serial number.
FIXTURE_INPUT_VALUE = "99999999"

DOC_CONSTANTS = {
    "uspto-open-data": "USPTO_ODP_DOCS",
    "uspto-patent-assignment": "USPTO_ODP_DOCS",
    "uspto-tsdr": "USPTO_TSDR_DOCS",
    "epo-ops": "EPO_OPS_DOCS",
}


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "patents_trademarks_runner",
        ROOT / "docker" / "patents_trademarks" / "runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_function(module, source: str):
    return getattr(module, "query_" + source.replace("-", "_"))


def _expected_endpoint(runner, source: str, value: str) -> str:
    if source == "uspto-open-data":
        return runner.USPTO_ODP_SEARCH_URL + "?" + urllib.parse.urlencode(
            {"q": value, "rows": "25", "start": "0"}
        )
    if source == "uspto-patent-assignment":
        return runner.USPTO_ODP_ASSIGNMENT_URL.format(application_number=value)
    if source == "uspto-tsdr":
        return runner.USPTO_TSDR_STATUS_URL.format(serial=value)
    if source == "epo-ops":
        return runner.EPO_OPS_SEARCH_URL + "?" + urllib.parse.urlencode({"q": value})
    raise AssertionError(source)


# -- subject extraction --------------------------------------------------------


def test_extract_subject_uspto_open_data():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "application"}]}
    assert _extract_subject(data, "uspto-open-data") == "USPTO_ODP:" + FIXTURE_INPUT_VALUE


def test_extract_subject_uspto_patent_assignment():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "assignment"}]}
    assert (
        _extract_subject(data, "uspto-patent-assignment")
        == "USPTO_ASSIGNMENT:" + FIXTURE_INPUT_VALUE
    )


def test_extract_subject_uspto_tsdr():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "case"}]}
    assert _extract_subject(data, "uspto-tsdr") == "USPTO_TSDR:" + FIXTURE_INPUT_VALUE


def test_extract_subject_epo_ops():
    data = {"records": [{"record_id": "EP1000000A1", "detail": "publication"}]}
    assert _extract_subject(data, "epo-ops") == "EPO:EP1000000A1"


def test_extract_subject_without_a_record_falls_back_to_source():
    """A payload with no record never claims a record subject."""
    for source in SUPPORTED_SOURCES:
        assert _extract_subject({"records": [], "record_count": 0}, source) == source


# -- record type, identifier, jurisdiction and kind ----------------------------


def test_extract_record_type():
    cases = [
        ("uspto-open-data", "uspto_open_data_patent_application"),
        ("uspto-patent-assignment", "uspto_patent_assignment"),
        ("uspto-tsdr", "uspto_tsdr_trademark_case"),
        ("epo-ops", "epo_ops_publication"),
        ("patentsview", None),
        ("unknown-source", None),
    ]
    for source, expected in cases:
        record = None if source in ("patentsview", "unknown-source") else {"record_id": "x"}
        data = {"records": [record] if record else []}
        result = _extract_record_type(data, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


def test_extract_identifier_prefers_the_query():
    assert _extract_identifier({"query": FIXTURE_INPUT_VALUE}, "uspto-open-data") == FIXTURE_INPUT_VALUE
    assert _extract_identifier({"records": [{"record_id": "x"}]}, "uspto-open-data") == "x"
    assert _extract_identifier({"records": []}, "uspto-open-data") is None


def test_extract_jurisdiction():
    assert _extract_jurisdiction("uspto-open-data") == "US"
    assert _extract_jurisdiction("uspto-patent-assignment") == "US"
    assert _extract_jurisdiction("uspto-tsdr") == "US"
    assert _extract_jurisdiction("epo-ops") == "EP"
    assert _extract_jurisdiction("patentsview") is None


def test_extract_ip_kind():
    assert _extract_ip_kind("uspto-open-data") == "patent"
    assert _extract_ip_kind("uspto-patent-assignment") == "patent"
    assert _extract_ip_kind("uspto-tsdr") == "trademark"
    assert _extract_ip_kind("epo-ops") == "patent"
    assert _extract_ip_kind("patentsview") is None


# -- details extraction --------------------------------------------------------


def test_extract_details_uspto_open_data():
    data = {
        "api_source": "USPTO Open Data Portal Patent Search API",
        "api_documentation": "https://data.uspto.gov/apis",
        "endpoint": "https://api.uspto.gov/api/v1/patent/applications/search?q=99999999",
        "query": FIXTURE_INPUT_VALUE,
        "record_count": 1,
        "records": [
            {
                "record_id": FIXTURE_INPUT_VALUE,
                "detail": "application",
                "application_number": FIXTURE_INPUT_VALUE,
                "patent_number": "9999999",
                "invention_title": "Synthetic widget assembly",
                "inventors": ["Synthetic Inventor"],
                "applicants": ["Synthetic Applicant Corporation"],
            }
        ],
    }
    result = _extract_details(data, "uspto-open-data")
    assert result["patent_number"] == "9999999"
    assert result["invention_title"] == "Synthetic widget assembly"
    assert result["inventors"] == ["Synthetic Inventor"]
    assert result["record_count"] == 1
    assert result["truncated"] is False


def test_extract_details_uspto_patent_assignment():
    data = {
        "api_source": "USPTO Open Data Portal Patent Assignment Data",
        "application_number": FIXTURE_INPUT_VALUE,
        "records": [
            {
                "record_id": FIXTURE_INPUT_VALUE,
                "detail": "assignment",
                "assignment": {"synthetic": True},
            }
        ],
    }
    result = _extract_details(data, "uspto-patent-assignment")
    assert result["application_number"] == FIXTURE_INPUT_VALUE
    assert result["assignment"] == {"synthetic": True}


def test_extract_details_uspto_tsdr():
    data = {
        "api_source": "USPTO TSDR Trademark Case Status API",
        "records": [
            {
                "record_id": FIXTURE_INPUT_VALUE,
                "detail": "case",
                "mark_verbal_element_text": "SYNTHETIC MARK",
                "registration_number": "9999999",
                "status_description": "Registered",
            }
        ],
    }
    result = _extract_details(data, "uspto-tsdr")
    assert result["mark_verbal_element_text"] == "SYNTHETIC MARK"
    assert result["registration_number"] == "9999999"
    assert result["status_description"] == "Registered"


def test_extract_details_epo_ops():
    data = {
        "api_source": "EPO Open Patent Services (OPS) published-data search",
        "total_result_count": "1",
        "records": [
            {
                "record_id": "EP1000000A1",
                "detail": "publication",
                "country": "EP",
                "doc_number": "1000000",
                "kind": "A1",
            }
        ],
    }
    result = _extract_details(data, "epo-ops")
    assert result["total_result_count"] == "1"
    assert result["country"] == "EP"
    assert result["doc_number"] == "1000000"
    assert result["kind"] == "A1"


def test_extract_details_without_a_record_is_none():
    assert _extract_details({"records": []}, "uspto-open-data") is None


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = PatentsTrademarksFinding(
        subject="USPTO_ODP:" + FIXTURE_INPUT_VALUE,
        source="uspto-open-data",
        record_type="uspto_open_data_patent_application",
        identifier=FIXTURE_INPUT_VALUE,
        jurisdiction="US",
        ip_kind="patent",
        date="2026-10-16",
        details={"patent_number": "9999999"},
        raw_evidence={"records": [{"record_id": FIXTURE_INPUT_VALUE}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:uspto-open-data",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from uspto-open-data"],
        ),
    )
    assert finding.entity_type == EntityType.INTELLECTUAL_PROPERTY_RECORD
    assert finding.entity_type.value == "intellectual_property_record"
    assert finding.attributes["source"] == "uspto-open-data"
    assert finding.attributes["jurisdiction"] == "US"
    assert finding.attributes["ip_kind"] == "patent"
    assert finding.subject == "USPTO_ODP:" + FIXTURE_INPUT_VALUE
    assert finding.identifier == FIXTURE_INPUT_VALUE


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    runner = _load_runner()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 7
    assert set(sources) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    assert tuple(runner.SUPPORTED_SUB_SOURCES) == tuple(SUPPORTED_SOURCES)
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES

    by_source = {s["source"]: s for s in fixture["sources"]}
    for source in ("uspto-open-data", "uspto-patent-assignment", "uspto-tsdr"):
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
        # The recorded artefact URL is the one the runner actually requests, so a
        # fixture can never point at an endpoint the runner does not use.
        assert entry["data"]["endpoint"] == _expected_endpoint(
            runner, source, FIXTURE_INPUT_VALUE
        ), source
        assert entry["data"]["api_documentation"] == getattr(runner, DOC_CONSTANTS[source]), source
        assert entry["data"]["query"] == FIXTURE_INPUT_VALUE, source


def test_fixture_dropped_candidate_is_skipped_with_its_exact_reason(monkeypatch):
    """A dropped candidate is an auditable skip, never a fabricated call."""
    fixture = load_fixture()
    runner = _load_runner()
    by_source = {s["source"]: s for s in fixture["sources"]}
    for name, reason in UNSUPPORTED_SUB_SOURCES.items():
        entry = by_source[name]
        assert entry["skipped"] is True, name
        assert entry["skip_reason"] == reason, name
        assert entry["raw_hash"] is None, name
        assert entry["data"] is None, name
    assert by_source["patentsview"]["skip_reason"] == runner.UNSUPPORTED_SUB_SOURCES["patentsview"]

    # The recorded key-required skip reason is exactly what the runner produces.
    monkeypatch.delenv("EPO_OPS_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("EPO_OPS_CONSUMER_SECRET", raising=False)
    assert by_source["epo-ops"]["skip_reason"] == runner.query_epo_ops(
        FIXTURE_INPUT_VALUE
    ).skip_reason


def test_fixture_uses_only_synthetic_values():
    """The fixture is synthetic and must not read as captured live output."""
    fixture = load_fixture()
    assert fixture["input_type"] == "intellectual_property"
    assert fixture["input_value"] == FIXTURE_INPUT_VALUE
    for entry in fixture["sources"]:
        if not entry["data"]:
            continue
        assert entry["data"]["query"] == fixture["input_value"]


# -- run result parsing --------------------------------------------------------


def _request(value: str = FIXTURE_INPUT_VALUE) -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=SeedType.INTELLECTUAL_PROPERTY, value=value),
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
            "input_type": "intellectual_property",
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


@parser_test("patents_trademarks")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = PatentsTrademarksAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 7

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)

    open_data = by_source["uspto-open-data"]
    assert open_data.value == "USPTO_ODP:" + FIXTURE_INPUT_VALUE
    assert open_data.subject == "USPTO_ODP:" + FIXTURE_INPUT_VALUE
    assert open_data.record_type == "uspto_open_data_patent_application"
    assert open_data.identifier == FIXTURE_INPUT_VALUE
    assert open_data.jurisdiction == "US"
    assert open_data.ip_kind == "patent"
    assert open_data.attributes["details"]["invention_title"] == "Synthetic widget assembly"
    assert open_data.attributes["details"]["patent_number"] == "9999999"
    assert open_data.attributes["details"]["inventors"] == ["Synthetic Inventor"]
    assert open_data.attributes["date"] == fixture["sources"][0]["timestamp"][:10]

    assignment = by_source["uspto-patent-assignment"]
    assert assignment.value == "USPTO_ASSIGNMENT:" + FIXTURE_INPUT_VALUE
    assert assignment.record_type == "uspto_patent_assignment"
    assert assignment.jurisdiction == "US"
    assert assignment.attributes["details"]["assignment"]["synthetic"] is True
    assert assignment.attributes["details"]["application_number"] == FIXTURE_INPUT_VALUE

    tsdr = by_source["uspto-tsdr"]
    assert tsdr.value == "USPTO_TSDR:" + FIXTURE_INPUT_VALUE
    assert tsdr.record_type == "uspto_tsdr_trademark_case"
    assert tsdr.ip_kind == "trademark"
    assert tsdr.attributes["details"]["mark_verbal_element_text"] == "SYNTHETIC MARK"
    assert tsdr.attributes["details"]["registration_number"] == "9999999"

    epo = by_source["epo-ops"]
    assert epo.value == "epo-ops:skipped"
    assert epo.record_type is None
    assert epo.attributes["details"]["skipped"] is True
    assert "EPO_OPS_CONSUMER_KEY" in epo.attributes["details"]["reason"]

    patentsview = by_source["patentsview"]
    assert patentsview.value == "patentsview:skipped"
    assert patentsview.record_type is None
    assert patentsview.attributes["details"] == {
        "skipped": True,
        "reason": UNSUPPORTED_SUB_SOURCES["patentsview"],
    }

    for finding in result.findings:
        assert isinstance(finding, PatentsTrademarksFinding)
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.INTELLECTUAL_PROPERTY_RECORD)
        assert finding.provenance.tool == "patents_trademarks"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80

    _assert_provenance_hash_invariant(result.findings)

    # A mixed runner payload must yield a real finding, a skip finding and an
    # error finding, each with the same provenance hash invariant.
    mixed = _payload(
        [
            _source(
                "uspto-open-data",
                data=fixture["sources"][0]["data"],
                raw_hash=fixture["sources"][0]["raw_hash"],
            ),
            _source(
                "uspto-tsdr",
                skipped=True,
                skip_reason="USPTO_TSDR_API_KEY is not set for this run",
                http_status=0,
            ),
            _source(
                "epo-ops",
                http_status=503,
                error="HTTP 503: Service Unavailable",
            ),
        ]
    )
    mixed_result = adapter.parse(_request(), Path("."), mixed, "", 0)

    assert mixed_result.status == "succeeded"
    assert len(mixed_result.findings) == 3
    mixed_by_source = {f.attributes["source"]: f for f in mixed_result.findings}

    ok_finding = mixed_by_source["uspto-open-data"]
    assert ok_finding.value == "USPTO_ODP:" + FIXTURE_INPUT_VALUE
    assert ok_finding.record_type == "uspto_open_data_patent_application"

    skipped_finding = mixed_by_source["uspto-tsdr"]
    assert skipped_finding.value == "uspto-tsdr:skipped"
    assert skipped_finding.record_type is None
    assert skipped_finding.attributes["details"] == {
        "skipped": True,
        "reason": "USPTO_TSDR_API_KEY is not set for this run",
    }
    assert "Skipped: USPTO_TSDR_API_KEY is not set for this run" in skipped_finding.provenance.notes

    error_finding = mixed_by_source["epo-ops"]
    assert error_finding.value == "epo-ops:error"
    assert error_finding.record_type is None
    assert error_finding.attributes["details"] == {
        "error": "HTTP 503: Service Unavailable",
        "http_status": 503,
    }
    assert "Error: HTTP 503: Service Unavailable" in error_finding.provenance.notes

    for finding in mixed_result.findings:
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.INTELLECTUAL_PROPERTY_RECORD)
    _assert_provenance_hash_invariant(mixed_result.findings)


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    reason = "USPTO_ODP_API_KEY is not set for this run"
    payload = _payload([_source("uspto-open-data", skipped=True, skip_reason=reason, http_status=0)])

    adapter = PatentsTrademarksAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "uspto-open-data"
    assert finding.value == "uspto-open-data:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": reason}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
    assert f"Skipped: {reason}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not a record."""
    payload = _payload(
        [_source("epo-ops", http_status=403, error="HTTP 403: Forbidden")]
    )

    adapter = PatentsTrademarksAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "epo-ops"
    assert finding.value == "epo-ops:error"
    assert finding.attributes["details"] == {
        "error": "HTTP 403: Forbidden",
        "http_status": 403,
    }
    assert "Error: HTTP 403: Forbidden" in finding.provenance.notes

    # A sub-source error must not be reported as a successful record.
    assert finding.record_type is None
    assert finding.attributes.get("raw_evidence") == {
        "error": "HTTP 403: Forbidden",
        "http_status": 403,
    }
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
        json.dumps(finding.attributes["raw_evidence"], sort_keys=True).encode()
    ).hexdigest()


def test_parse_no_match_produces_no_finding():
    """A source with no record must not be reported as a finding."""
    payload = _payload([_source("uspto-open-data", data=None, raw_hash=None)])

    adapter = PatentsTrademarksAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = PatentsTrademarksAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = PatentsTrademarksAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = PatentsTrademarksAdapter()
    assert adapter.supports(SeedType.INTELLECTUAL_PROPERTY)
    assert not adapter.supports(SeedType.NAME)
    assert not adapter.supports(SeedType.COMPANY_NAME)
    assert not adapter.supports(SeedType.CRYPTO_ADDRESS)


def test_adapter_build_command_intellectual_property():
    adapter = PatentsTrademarksAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.INTELLECTUAL_PROPERTY, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["intellectual_property", "test_val"]
    assert adapter.descriptor.input_types == [SeedType.INTELLECTUAL_PROPERTY]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "patents_trademarks" in registry

    descriptor = registry["patents_trademarks"].descriptor
    assert descriptor.name == "patents_trademarks"
    assert descriptor.input_types == [SeedType.INTELLECTUAL_PROPERTY]
    assert descriptor.output_types == [EntityType.INTELLECTUAL_PROPERTY_RECORD]
    assert descriptor.docker_image == "aletheia/patents-trademarks:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == [
        "USPTO_ODP_API_KEY",
        "USPTO_TSDR_API_KEY",
        "EPO_OPS_CONSUMER_KEY",
        "EPO_OPS_CONSUMER_SECRET",
    ]
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)
    assert descriptor.upstream.endswith("docker/patents_trademarks")


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
    assert kinds["uspto-open-data"] == "http_api"
    assert kinds["epo-ops"] == "http_api"
    assert kinds["patentsview"] == "dropped"
    assert inventory["dropped_sub_sources"] == [
        "euipo-esearch-plus",
        "google-patents-bigquery",
        "patentsview",
    ]
    for entry in inventory["sub_sources"]:
        if entry["kind"] == "dropped":
            assert entry["endpoint"] is None
            assert entry["credential_configured"] is None


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
    for source in UNSUPPORTED_SUB_SOURCES:
        assert callable(_runner_function(runner, source))
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
    """Every implemented sub-source queries one documented HTTPS endpoint."""
    runner = _load_runner()
    endpoint_constants = {
        "uspto-open-data": "USPTO_ODP_SEARCH_URL",
        "uspto-patent-assignment": "USPTO_ODP_ASSIGNMENT_URL",
        "uspto-tsdr": "USPTO_TSDR_STATUS_URL",
        "epo-ops": "EPO_OPS_SEARCH_URL",
    }
    for source, constant in endpoint_constants.items():
        endpoint = getattr(runner, constant)
        assert endpoint.startswith("https://"), source
        function_source = inspect.getsource(_runner_function(runner, source))
        assert constant in function_source, source


def test_runner_skips_key_required_sources_without_their_keys(monkeypatch):
    runner = _load_runner()
    for env in (
        "USPTO_ODP_API_KEY",
        "USPTO_TSDR_API_KEY",
        "EPO_OPS_CONSUMER_KEY",
        "EPO_OPS_CONSUMER_SECRET",
    ):
        monkeypatch.delenv(env, raising=False)

    open_data = runner.query_uspto_open_data(FIXTURE_INPUT_VALUE)
    assert open_data.skipped is True
    assert "USPTO_ODP_API_KEY" in open_data.skip_reason

    assignment = runner.query_uspto_patent_assignment(FIXTURE_INPUT_VALUE)
    assert assignment.skipped is True
    assert "USPTO_ODP_API_KEY" in assignment.skip_reason

    tsdr = runner.query_uspto_tsdr(FIXTURE_INPUT_VALUE)
    assert tsdr.skipped is True
    assert "USPTO_TSDR_API_KEY" in tsdr.skip_reason

    epo = runner.query_epo_ops(FIXTURE_INPUT_VALUE)
    assert epo.skipped is True
    assert "EPO_OPS_CONSUMER_KEY" in epo.skip_reason


def test_runner_skips_a_non_numeric_seed_for_number_keyed_routes(monkeypatch):
    """A name is never sent to an endpoint that documents a numeric path segment."""
    runner = _load_runner()
    monkeypatch.setenv("USPTO_ODP_API_KEY", "test-key")
    monkeypatch.setenv("USPTO_TSDR_API_KEY", "test-key")

    assignment = runner.query_uspto_patent_assignment("SyntheticApplicantName")
    assert assignment.skipped is True
    assert "application number" in assignment.skip_reason

    tsdr = runner.query_uspto_tsdr("SyntheticApplicantName")
    assert tsdr.skipped is True
    assert "serial number" in tsdr.skip_reason


def test_runner_parses_the_documented_odp_shape(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("USPTO_ODP_API_KEY", "odp_test_key")
    payload = {
        "count": 1,
        "patents": [
            {
                "applicationNumberText": FIXTURE_INPUT_VALUE,
                "patentNumber": "9999999",
                "inventionTitle": "Synthetic widget assembly",
                "inventors": [{"inventorNameText": "Synthetic Inventor"}],
                "applicants": [{"applicantNameText": "Synthetic Applicant Corporation"}],
            }
        ],
    }
    monkeypatch.setattr(runner, "_fetch_json", lambda *a, **k: (payload, 200, None))
    result = runner.query_uspto_open_data(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert result.http_status == 200
    assert result.data["records"][0]["application_number"] == FIXTURE_INPUT_VALUE
    assert result.data["records"][0]["inventors"] == ["Synthetic Inventor"]
    assert result.data["record_count"] == 1


def test_runner_parses_the_documented_tsdr_shape(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("USPTO_TSDR_API_KEY", "tsdr_test_key")
    xml = (
        "<CaseStatusData>"
        "<ApplicationNumber>" + FIXTURE_INPUT_VALUE + "</ApplicationNumber>"
        "<RegistrationNumber>9999999</RegistrationNumber>"
        "<MarkVerbalElementText>SYNTHETIC MARK</MarkVerbalElementText>"
        "<MarkCurrentStatusExternalDescriptionText>Registered</MarkCurrentStatusExternalDescriptionText>"
        "</CaseStatusData>"
    )
    monkeypatch.setattr(runner, "_fetch_text", lambda *a, **k: (xml, 200, None))
    result = runner.query_uspto_tsdr(FIXTURE_INPUT_VALUE)

    assert result.error is None
    record = result.data["records"][0]
    assert record["mark_verbal_element_text"] == "SYNTHETIC MARK"
    assert record["registration_number"] == "9999999"
    assert record["status_description"] == "Registered"


def test_runner_parses_the_documented_epo_ops_shape(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY", "consumer")
    monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET", "secret")
    monkeypatch.setattr(runner, "_fetch_json", lambda *a, **k: ({"access_token": "token"}, 200, None))
    xml = (
        '<ops:world-patent-data xmlns:ops="http://ops.epo.org">'
        '<ops:biblio-search total-result-count="1">'
        "<ops:search-result>"
        "<ops:publication-reference>"
        '<document-id document-id-type="docdb">'
        "<country>EP</country><doc-number>1000000</doc-number><kind>A1</kind>"
        "</document-id>"
        "</ops:publication-reference>"
        "</ops:search-result>"
        "</ops:biblio-search>"
        "</ops:world-patent-data>"
    )
    monkeypatch.setattr(runner, "_fetch_text", lambda *a, **k: (xml, 200, None))
    result = runner.query_epo_ops("EP1000000")

    assert result.error is None
    assert result.data["record_count"] == 1
    assert result.data["records"][0]["record_id"] == "EP1000000A1"
    assert result.data["records"][0]["country"] == "EP"
    assert result.data["total_result_count"] == "1"


def test_runner_records_an_http_error_without_leaking_the_key(monkeypatch):
    """A failing keyed request is recorded as an error with no key in the output."""
    runner = _load_runner()
    monkeypatch.setenv("USPTO_ODP_API_KEY", "super-secret-key")
    monkeypatch.setattr(runner, "_fetch_json", lambda *a, **k: (None, 403, "HTTP 403: Forbidden"))
    result = runner.query_uspto_open_data(FIXTURE_INPUT_VALUE)
    assert result.error == "HTTP 403: Forbidden"
    assert result.data is None
