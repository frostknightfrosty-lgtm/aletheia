"""Parser + fixture tests for the code_search batch adapter."""

import hashlib
import importlib.util
import inspect
import io
import json
import sys
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

from aletheia.adapters.code_search import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    CodeSearchAdapter,
    TechnicalFinding,
    _extract_details,
    _extract_finding_kind,
    _extract_match_mode,
    _extract_query,
    _extract_record_type,
    _extract_subject,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIXTURE_PATH = "tests/fixtures/code_search.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = ("debian-code-search",)
DROPPED_SOURCES = ("gitlab-search", "publicwww")

FIXTURE_INPUT_VALUE = "AletheiaSyntheticCodeQuery"

# The documented endpoint constant the implemented sub-source resolves its URL
# from, plus the documentation constants, so the fixture can never point at an
# endpoint the runner does not use.
ENDPOINT_CONSTANTS = {
    "debian-code-search": "DEBIAN_CODE_SEARCH_SEARCH_URL",
}

DOC_CONSTANTS = {
    "debian-code-search": "DEBIAN_CODE_SEARCH_DOCS",
}

OPENAPI_CONSTANTS = {
    "debian-code-search": "DEBIAN_CODE_SEARCH_OPENAPI",
}


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "code_search_runner",
        ROOT / "docker" / "code_search" / "runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_function(module, source: str):
    return getattr(module, "query_" + source.replace("-", "_"))


# -- subject extraction --------------------------------------------------------


def test_extract_subject_debian_code_search():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "summary"}]}
    assert _extract_subject(data, "debian-code-search") == "DCS:" + FIXTURE_INPUT_VALUE


def test_extract_subject_without_a_record_falls_back_to_source():
    """A payload with no record never claims a record subject."""
    for source in SUPPORTED_SOURCES:
        assert _extract_subject({"records": [], "record_count": 0}, source) == source


# -- finding kind, record type, query and match-mode extraction ----------------


def test_extract_finding_kind_and_record_type():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE}]}
    assert _extract_finding_kind(data, "debian-code-search") == "source_code_search_match"
    assert _extract_record_type(data, "debian-code-search") == "debian_code_search_match"
    assert _extract_finding_kind({"records": []}, "debian-code-search") is None
    assert _extract_record_type({"records": []}, "debian-code-search") is None
    # A dropped candidate has no typed kind at all.
    assert _extract_finding_kind(data, "gitlab-search") is None
    assert _extract_record_type(data, "publicwww") is None


def test_extract_query_and_match_mode():
    assert _extract_query({"query": FIXTURE_INPUT_VALUE}, "debian-code-search") == FIXTURE_INPUT_VALUE
    assert _extract_query({"records": [{"record_id": "x"}]}, "debian-code-search") == "x"
    assert _extract_query({}, "debian-code-search") is None
    assert _extract_match_mode({"match_mode": "literal"}, "debian-code-search") == "literal"
    assert _extract_match_mode({"match_mode": None}, "debian-code-search") is None
    assert _extract_match_mode({}, "debian-code-search") is None


# -- details extraction --------------------------------------------------------


def test_extract_details_debian_code_search():
    data = {
        "api_source": "Debian Code Search (GET /api/v1/search)",
        "api_documentation": "https://codesearch.debian.net/",
        "openapi_specification": "https://codesearch.debian.net/openapi.json",
        "endpoint": "https://codesearch.debian.net/api/v1/search?query=" + FIXTURE_INPUT_VALUE,
        "record_count": 1,
        "truncated": False,
        "records": [
            {
                "record_id": FIXTURE_INPUT_VALUE,
                "detail": "verbatim response document",
                "response_type": "object",
            }
        ],
    }
    result = _extract_details(data, "debian-code-search")
    assert result["openapi_specification"] == "https://codesearch.debian.net/openapi.json"
    assert result["record_count"] == 1
    assert result["response_type"] == "object"
    assert result["truncated"] is False


def test_extract_details_without_a_record_is_none():
    assert _extract_details({"records": []}, "debian-code-search") is None


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = TechnicalFinding(
        subject="DCS:" + FIXTURE_INPUT_VALUE,
        source="debian-code-search",
        finding_kind="source_code_search_match",
        record_type="debian_code_search_match",
        query=FIXTURE_INPUT_VALUE,
        match_mode="literal",
        date="2026-10-16",
        details={"record_count": 1},
        raw_evidence={"records": [{"record_id": FIXTURE_INPUT_VALUE}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:debian-code-search",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from debian-code-search"],
        ),
    )
    assert finding.entity_type == EntityType.TECHNICAL_FINDING
    assert finding.entity_type.value == "technical_finding"
    assert finding.attributes["source"] == "debian-code-search"
    assert finding.attributes["finding_kind"] == "source_code_search_match"
    assert finding.subject == "DCS:" + FIXTURE_INPUT_VALUE
    assert finding.query == FIXTURE_INPUT_VALUE
    assert finding.match_mode == "literal"


# -- fixture -------------------------------------------------------------------


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    runner = _load_runner()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 3
    assert set(sources) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    assert tuple(runner.SUPPORTED_SUB_SOURCES) == tuple(SUPPORTED_SOURCES)
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES

    by_source = {s["source"]: s for s in fixture["sources"]}
    entry = by_source["debian-code-search"]
    assert entry["skipped"] is False
    assert entry["error"] is None
    assert entry["http_status"] == 200
    assert entry["data"]
    # The fixture hash uses the same convention as the runner: sha256 over
    # json.dumps(data, sort_keys=True).
    assert entry["raw_hash"] == hashlib.sha256(
        json.dumps(entry["data"], sort_keys=True).encode()
    ).hexdigest()
    # The recorded artefact URL is the one the runner actually requests, so a
    # fixture can never point at an endpoint the runner does not use.
    assert entry["data"]["endpoint"] == (
        getattr(runner, ENDPOINT_CONSTANTS["debian-code-search"])
        + "?"
        + "query="
        + FIXTURE_INPUT_VALUE
    )
    assert entry["data"]["api_documentation"] == getattr(runner, DOC_CONSTANTS["debian-code-search"])
    assert entry["data"]["openapi_specification"] == getattr(
        runner, OPENAPI_CONSTANTS["debian-code-search"]
    )
    assert entry["data"]["query"] == FIXTURE_INPUT_VALUE


def test_fixture_dropped_candidates_are_skipped_with_their_exact_reasons():
    """Each dropped candidate is an auditable skip, never a fabricated call."""
    fixture = load_fixture()
    runner = _load_runner()
    by_source = {s["source"]: s for s in fixture["sources"]}
    assert set(UNSUPPORTED_SUB_SOURCES) == set(DROPPED_SOURCES)
    for name, reason in UNSUPPORTED_SUB_SOURCES.items():
        entry = by_source[name]
        assert entry["skipped"] is True, name
        assert entry["skip_reason"] == reason, name
        assert entry["raw_hash"] is None, name
        assert entry["data"] is None, name
        # The recorded reason is exactly what the runner reports.
        assert entry["skip_reason"] == runner.UNSUPPORTED_SUB_SOURCES[name], name


def test_fixture_uses_only_synthetic_values():
    """The fixture is synthetic and must not read as captured live output."""
    fixture = load_fixture()
    assert "Synthetic" in fixture["input_value"]
    for entry in fixture["sources"]:
        if not entry["data"]:
            continue
        assert entry["data"]["query"] == fixture["input_value"]


# -- run result parsing --------------------------------------------------------


def _request(value: str = FIXTURE_INPUT_VALUE) -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.NAME, value=value), legal_only=True
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
            "input_type": "name",
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


@parser_test("code_search")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = CodeSearchAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 3

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)

    debian = by_source["debian-code-search"]
    assert debian.value == "DCS:" + FIXTURE_INPUT_VALUE
    assert debian.subject == "DCS:" + FIXTURE_INPUT_VALUE
    assert debian.finding_kind == "source_code_search_match"
    assert debian.record_type == "debian_code_search_match"
    assert debian.query == FIXTURE_INPUT_VALUE
    assert debian.attributes["finding_kind"] == "source_code_search_match"
    assert debian.attributes["details"]["record_count"] == 1
    assert debian.attributes["details"]["openapi_specification"] == (
        "https://codesearch.debian.net/openapi.json"
    )
    assert debian.attributes["date"] == fixture["sources"][0]["timestamp"][:10]

    for name in DROPPED_SOURCES:
        dropped = by_source[name]
        assert dropped.value == name + ":skipped"
        assert dropped.finding_kind is None
        assert dropped.record_type is None
        assert dropped.attributes["details"] == {
            "skipped": True,
            "reason": UNSUPPORTED_SUB_SOURCES[name],
        }

    for finding in result.findings:
        assert isinstance(finding, TechnicalFinding)
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.TECHNICAL_FINDING)
        assert finding.provenance.tool == "code_search"
        assert finding.provenance.source_url == "sub-source:" + finding.attributes["source"]
        assert finding.provenance.confidence == 0.80

    _assert_provenance_hash_invariant(result.findings)

    # A mixed runner payload must yield a real finding, a skip finding and an
    # error finding, each with the same provenance hash invariant.
    mixed = _payload(
        [
            _source(
                "debian-code-search",
                data=fixture["sources"][0]["data"],
                raw_hash=fixture["sources"][0]["raw_hash"],
            ),
            _source(
                "gitlab-search",
                skipped=True,
                skip_reason="gitlab-search is documented as authentication-required for this run",
                http_status=0,
            ),
            _source(
                "publicwww",
                http_status=503,
                error="HTTP 503: Service Unavailable",
            ),
        ]
    )
    mixed_result = adapter.parse(_request(), Path("."), mixed, "", 0)

    assert mixed_result.status == "succeeded"
    assert len(mixed_result.findings) == 3
    mixed_by_source = {f.attributes["source"]: f for f in mixed_result.findings}

    ok_finding = mixed_by_source["debian-code-search"]
    assert ok_finding.value == "DCS:" + FIXTURE_INPUT_VALUE
    assert ok_finding.finding_kind == "source_code_search_match"
    assert ok_finding.record_type == "debian_code_search_match"

    skipped_finding = mixed_by_source["gitlab-search"]
    assert skipped_finding.value == "gitlab-search:skipped"
    assert skipped_finding.finding_kind is None
    assert skipped_finding.attributes["details"] == {
        "skipped": True,
        "reason": "gitlab-search is documented as authentication-required for this run",
    }
    assert (
        "Skipped: gitlab-search is documented as authentication-required for this run"
        in skipped_finding.provenance.notes
    )

    error_finding = mixed_by_source["publicwww"]
    assert error_finding.value == "publicwww:error"
    assert error_finding.finding_kind is None
    assert error_finding.attributes["details"] == {
        "error": "HTTP 503: Service Unavailable",
        "http_status": 503,
    }
    assert "Error: HTTP 503: Service Unavailable" in error_finding.provenance.notes

    for finding in mixed_result.findings:
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.TECHNICAL_FINDING)
    _assert_provenance_hash_invariant(mixed_result.findings)


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    reason = "PublicWWW is paid-only for this run"
    payload = _payload([_source("publicwww", skipped=True, skip_reason=reason, http_status=0)])

    adapter = CodeSearchAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "publicwww"
    assert finding.value == "publicwww:skipped"
    assert finding.finding_kind is None
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": reason}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
    assert f"Skipped: {reason}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not a record."""
    payload = _payload(
        [_source("debian-code-search", http_status=403, error="HTTP 403: Forbidden")]
    )

    adapter = CodeSearchAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "debian-code-search"
    assert finding.value == "debian-code-search:error"
    assert finding.finding_kind is None
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
    payload = _payload([_source("debian-code-search", data=None, raw_hash=None)])

    adapter = CodeSearchAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = CodeSearchAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = CodeSearchAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = CodeSearchAdapter()
    assert adapter.supports(SeedType.NAME)
    assert not adapter.supports(SeedType.EMAIL)
    assert not adapter.supports(SeedType.DOMAIN)
    assert not adapter.supports(SeedType.CRYPTO_ADDRESS)


def test_adapter_input_types_and_build_command():
    adapter = CodeSearchAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["name", "test_val"]
    assert adapter.descriptor.input_types == [SeedType.NAME]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "code_search" in registry

    descriptor = registry["code_search"].descriptor
    assert descriptor.name == "code_search"
    assert descriptor.input_types == [SeedType.NAME]
    assert descriptor.output_types == [EntityType.TECHNICAL_FINDING]
    assert descriptor.docker_image == "aletheia/code-search:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == ["DEBIAN_CODE_SEARCH_API_KEY"]
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)
    assert descriptor.upstream.endswith("docker/code_search")


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
    assert kinds["debian-code-search"] == "http_api"
    assert kinds["gitlab-search"] == "dropped"
    assert kinds["publicwww"] == "dropped"
    assert inventory["dropped_sub_sources"] == ["gitlab-search", "publicwww"]

    debian = next(e for e in inventory["sub_sources"] if e["source"] == "debian-code-search")
    assert debian["endpoint"] == "https://codesearch.debian.net/api/v1/search"
    assert debian["credential_env"] == "DEBIAN_CODE_SEARCH_API_KEY"
    assert isinstance(debian["credential_configured"], bool)
    assert debian["usable"] is True


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
        assert callable(_runner_function(runner, source))
    for source in DROPPED_SOURCES:
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


def test_runner_supported_source_cites_a_documented_endpoint():
    """The implemented sub-source queries one documented HTTPS endpoint."""
    runner = _load_runner()
    endpoint = runner.DEBIAN_CODE_SEARCH_SEARCH_URL
    assert endpoint.startswith("https://")
    function_source = inspect.getsource(_runner_function(runner, "debian-code-search"))
    assert "DEBIAN_CODE_SEARCH_SEARCH_URL" in function_source
    assert "DEBIAN_CODE_SEARCH_OPENAPI" in function_source


def test_runner_skips_without_its_key(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv("DEBIAN_CODE_SEARCH_API_KEY", raising=False)
    result = runner.query_debian_code_search(FIXTURE_INPUT_VALUE)
    assert result.skipped is True
    assert "DEBIAN_CODE_SEARCH_API_KEY" in result.skip_reason
    assert result.data is None


def test_runner_dropped_candidates_report_their_exact_reason():
    runner = _load_runner()
    assert (
        runner.query_gitlab_search(FIXTURE_INPUT_VALUE).skip_reason
        == UNSUPPORTED_SUB_SOURCES["gitlab-search"]
    )
    assert (
        runner.query_publicwww(FIXTURE_INPUT_VALUE).skip_reason
        == UNSUPPORTED_SUB_SOURCES["publicwww"]
    )


def test_runner_uses_the_documented_header_without_leaking_the_key(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("DEBIAN_CODE_SEARCH_API_KEY", "test-key")
    captured = {}

    def fake_fetch(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return {"synthetic": [1, 2, 3]}, 200, None

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch)
    result = runner.query_debian_code_search(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert result.http_status == 200
    assert result.data["response"] == {"synthetic": [1, 2, 3]}
    assert result.data["records"][0]["record_id"] == FIXTURE_INPUT_VALUE
    assert captured["headers"] == {"x-dcs-apikey": "test-key"}
    assert "x-dcs-apikey" not in captured["url"]
    assert "test-key" not in captured["url"]
    assert result.raw_hash == hashlib.sha256(
        json.dumps(result.data, sort_keys=True).encode()
    ).hexdigest()


def test_runner_records_an_http_error(monkeypatch):
    """A failing keyed request is recorded as an error, not a record."""
    runner = _load_runner()
    monkeypatch.setenv("DEBIAN_CODE_SEARCH_API_KEY", "test-key")
    monkeypatch.setattr(
        runner, "_fetch_json", lambda *a, **k: (None, 403, "HTTP 403: Forbidden")
    )
    result = runner.query_debian_code_search(FIXTURE_INPUT_VALUE)
    assert result.error == "HTTP 403: Forbidden"
    assert result.data is None
