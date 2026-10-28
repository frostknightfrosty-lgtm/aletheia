"""Parser + fixture tests for the search_engines batch adapter."""

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

from aletheia.adapters.search_engines import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    SearchEnginesAdapter,
    WebSearchResult,
    _extract_details,
    _extract_record_type,
    _extract_snippet,
    _extract_subject,
    _extract_title,
    _extract_url,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIXTURE_PATH = "tests/fixtures/search_engines.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = (
    "marginalia",
    "common-crawl-index",
    "searxng",
)

FIXTURE_INPUT_VALUE = "SyntheticSearchQueryForFixture"

DOC_CONSTANTS = {
    "marginalia": "MARGINALIA_DOCS",
    "common-crawl-index": "COMMON_CRAWL_DOCS",
    "searxng": "SEARXNG_DOCS",
}


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "search_engines_runner",
        ROOT / "docker" / "search_engines" / "runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_function(module, source: str):
    return getattr(module, "query_" + source.replace("-", "_"))


def _expected_endpoint(runner, source: str, value: str) -> str:
    """The exact endpoint the runner resolves for a documented sub-source."""
    if source == "marginalia":
        return runner.MARGINALIA_API_URL + "?" + urllib.parse.urlencode({"query": value})
    if source == "common-crawl-index":
        return runner._common_crawl_endpoint(value)
    if source == "searxng":
        return runner._searxng_endpoint(value)
    raise AssertionError(source)


# -- subject / field extraction ------------------------------------------------


def test_extract_subject_marginalia():
    data = {"records": [{"record_id": "https://example.invalid/one", "detail": "r"}]}
    assert _extract_subject(data, "marginalia") == "MARGINALIA:https://example.invalid/one"


def test_extract_subject_common_crawl_index():
    data = {"records": [{"record_id": "https://example.invalid/two", "detail": "r"}]}
    assert _extract_subject(data, "common-crawl-index") == "CCINDEX:https://example.invalid/two"


def test_extract_subject_searxng():
    data = {"records": [{"record_id": "https://example.invalid/three", "detail": "r"}]}
    assert _extract_subject(data, "searxng") == "SEARXNG:https://example.invalid/three"


def test_extract_subject_without_a_record_falls_back_to_source():
    """A payload with no record never claims a record subject."""
    for source in SUPPORTED_SOURCES:
        assert _extract_subject({"records": [], "record_count": 0}, source) == source


def test_extract_record_type():
    cases = [
        ("marginalia", "marginalia_search_result"),
        ("common-crawl-index", "common_crawl_index_record"),
        ("searxng", "searxng_search_result"),
        ("unknown-source", None),
    ]
    for source, expected in cases:
        record = None if source == "unknown-source" else {"record_id": "x"}
        data = {"records": [record] if record else []}
        result = _extract_record_type(data, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


def test_extract_url_title_and_snippet():
    data = {
        "records": [
            {
                "record_id": "https://example.invalid/one",
                "url": "https://example.invalid/one",
                "title": "Example One",
                "snippet": "A description",
            }
        ]
    }
    assert _extract_url(data, "marginalia") == "https://example.invalid/one"
    assert _extract_title(data, "marginalia") == "Example One"
    assert _extract_snippet(data, "marginalia") == "A description"


def test_extract_url_falls_back_to_record_id():
    data = {"records": [{"record_id": "https://example.invalid/fallback"}]}
    assert _extract_url(data, "common-crawl-index") == "https://example.invalid/fallback"


def test_extract_helpers_without_a_record_are_none():
    for source in SUPPORTED_SOURCES:
        assert _extract_url({"records": []}, source) is None
        assert _extract_title({"records": []}, source) is None
        assert _extract_snippet({"records": []}, source) is None
        assert _extract_details({"records": []}, source) is None


# -- details extraction --------------------------------------------------------


def test_extract_details_marginalia():
    data = {
        "api_source": "Marginalia Search API (public search index)",
        "api_documentation": "https://about.marginalia-search.com/article/api/",
        "license": "CC-BY-NC-SA 4.0",
        "key_source": "documented-public-default",
        "endpoint": "https://api2.marginalia-search.com/search?query=" + FIXTURE_INPUT_VALUE,
        "query": FIXTURE_INPUT_VALUE,
        "record_count": 1,
        "truncated": False,
        "records": [
            {
                "record_id": "https://example.invalid/one",
                "detail": "Marginalia result Example One",
                "title": "Example One",
                "url": "https://example.invalid/one",
                "snippet": "A description",
            }
        ],
    }
    result = _extract_details(data, "marginalia")
    assert result["license"] == "CC-BY-NC-SA 4.0"
    assert result["key_source"] == "documented-public-default"
    assert result["title"] == "Example One"
    assert result["record_count"] == 1


def test_extract_details_common_crawl_index():
    data = {
        "api_source": "Common Crawl CDXJ/URL index (CC-MAIN-2026-39)",
        "crawl_id": "CC-MAIN-2026-39",
        "crawl_id_source": "https://commoncrawl.org/get-started",
        "endpoint": "https://index.commoncrawl.org/CC-MAIN-2026-39-index?url=x&output=json",
        "query": FIXTURE_INPUT_VALUE,
        "record_count": 1,
        "truncated": False,
        "records": [
            {
                "record_id": "https://example.invalid/one",
                "detail": "record",
                "urlkey": "invalid,example)/one",
                "timestamp": "20260101000000",
                "url": "https://example.invalid/one",
                "mime": "text/html",
                "status": "200",
                "digest": "SHA1:AAAABBBB",
                "length": "1234",
                "offset": "0",
                "filename": "crawl-data/x.warc.gz",
            }
        ],
    }
    result = _extract_details(data, "common-crawl-index")
    assert result["crawl_id"] == "CC-MAIN-2026-39"
    assert result["crawl_id_source"] == "https://commoncrawl.org/get-started"
    assert result["urlkey"] == "invalid,example)/one"
    assert result["status"] == "200"
    assert result["filename"] == "crawl-data/x.warc.gz"


def test_extract_details_searxng():
    data = {
        "api_source": "SearXNG (self-hosted instance, loopback only)",
        "api_documentation": "https://docs.searxng.org/dev/search_api.html",
        "instance": "http://127.0.0.1:8888",
        "pinned_commit": "1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4",
        "engines_config": ["duckduckgo", "brave", "wikipedia"],
        "engines_used": ["duckduckgo"],
        "unresponsive_engines": ["brave: HTTP timeout"],
        "number_of_results": 1,
        "endpoint": "http://127.0.0.1:8888/search?q=x&format=json",
        "query": FIXTURE_INPUT_VALUE,
        "record_count": 1,
        "truncated": False,
        "records": [
            {
                "record_id": "https://example.invalid/one",
                "detail": "SearXNG result One via duckduckgo",
                "title": "One",
                "url": "https://example.invalid/one",
                "snippet": "A description",
                "engine": "duckduckgo",
            }
        ],
    }
    result = _extract_details(data, "searxng")
    assert result["instance"] == "http://127.0.0.1:8888"
    assert result["pinned_commit"] == "1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4"
    assert result["engines_config"] == ["duckduckgo", "brave", "wikipedia"]
    assert result["engines_used"] == ["duckduckgo"]
    assert result["unresponsive_engines"] == ["brave: HTTP timeout"]
    assert result["engine"] == "duckduckgo"
    assert result["title"] == "One"


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = WebSearchResult(
        subject="MARGINALIA:https://example.invalid/one",
        source="marginalia",
        record_type="marginalia_search_result",
        title="Example One",
        url="https://example.invalid/one",
        snippet="A description",
        date="2026-10-16",
        details={"license": "CC-BY-NC-SA 4.0"},
        raw_evidence={"records": [{"record_id": "https://example.invalid/one"}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:marginalia",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from marginalia"],
        ),
    )
    assert finding.entity_type == EntityType.WEB_SEARCH_RESULT
    assert finding.entity_type.value == "web_search_result"
    assert finding.attributes["source"] == "marginalia"
    assert finding.attributes["url"] == "https://example.invalid/one"
    assert finding.subject == "MARGINALIA:https://example.invalid/one"
    assert finding.url == "https://example.invalid/one"


# -- fixture -------------------------------------------------------------------


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    runner = _load_runner()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 4
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
        # The recorded artefact URL is the one the runner actually requests, so a
        # fixture can never point at an endpoint the runner does not use.
        assert entry["data"]["endpoint"] == _expected_endpoint(
            runner, source, FIXTURE_INPUT_VALUE
        ), source
        assert entry["data"]["api_documentation"] == getattr(runner, DOC_CONSTANTS[source]), source
        assert entry["data"]["query"] == FIXTURE_INPUT_VALUE, source


def test_fixture_dropped_candidates_are_skipped_with_their_exact_reason():
    """The dropped candidates are auditable skips, never fabricated calls."""
    fixture = load_fixture()
    runner = _load_runner()
    by_source = {s["source"]: s for s in fixture["sources"]}
    assert set(UNSUPPORTED_SUB_SOURCES) == {"google-custom-search"}
    for name, reason in UNSUPPORTED_SUB_SOURCES.items():
        entry = by_source[name]
        assert entry["skipped"] is True, name
        assert entry["skip_reason"] == reason, name
        assert entry["raw_hash"] is None, name
        assert entry["data"] is None, name
        assert by_source[name]["skip_reason"] == runner.UNSUPPORTED_SUB_SOURCES[name], name


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


@parser_test("search_engines")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = SearchEnginesAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 4

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)

    marginalia = by_source["marginalia"]
    assert marginalia.value == "MARGINALIA:https://example.invalid/synthetic-marginalia-one"
    assert marginalia.subject == "MARGINALIA:https://example.invalid/synthetic-marginalia-one"
    assert marginalia.record_type == "marginalia_search_result"
    assert marginalia.url == "https://example.invalid/synthetic-marginalia-one"
    assert marginalia.title == "Synthetic Marginalia Result One"
    assert marginalia.attributes["details"]["license"] == "CC-BY-NC-SA 4.0"
    assert marginalia.attributes["date"] == fixture["sources"][0]["timestamp"][:10]

    crawl = by_source["common-crawl-index"]
    assert crawl.value == "CCINDEX:https://example.invalid/synthetic-page-one"
    assert crawl.record_type == "common_crawl_index_record"
    assert crawl.url == "https://example.invalid/synthetic-page-one"
    assert crawl.attributes["details"]["crawl_id"] == "CC-MAIN-2026-39"
    assert crawl.attributes["details"]["crawl_id_source"] == "https://commoncrawl.org/get-started"

    searxng = by_source["searxng"]
    assert searxng.value == "SEARXNG:https://example.invalid/synthetic-searxng-one"
    assert searxng.record_type == "searxng_search_result"
    assert searxng.url == "https://example.invalid/synthetic-searxng-one"
    assert searxng.title == "Synthetic SearXNG Result One"
    assert searxng.attributes["details"]["instance"] == "http://127.0.0.1:8888"
    assert searxng.attributes["details"]["pinned_commit"] == "1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4"
    assert searxng.attributes["details"]["engines_used"] == ["duckduckgo"]
    assert searxng.attributes["details"]["engine"] == "duckduckgo"

    # The dropped candidate is present as an auditable skip carrying the exact
    # documented reason; it is never reported as a successful record.
    gcs = by_source["google-custom-search"]
    assert gcs.value == "google-custom-search:skipped"
    assert gcs.record_type is None
    assert gcs.attributes["details"] == {
        "skipped": True,
        "reason": UNSUPPORTED_SUB_SOURCES["google-custom-search"],
    }

    for finding in result.findings:
        assert isinstance(finding, WebSearchResult)
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.WEB_SEARCH_RESULT)
        assert finding.provenance.tool == "search_engines"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80

    _assert_provenance_hash_invariant(result.findings)

    # A mixed runner payload must yield a real finding, a skip finding and an
    # error finding, each with the same provenance hash invariant.
    mixed = _payload(
        [
            _source(
                "marginalia",
                data=fixture["sources"][0]["data"],
                raw_hash=fixture["sources"][0]["raw_hash"],
            ),
            _source(
                "common-crawl-index",
                skipped=True,
                skip_reason="A documented skip for this run",
                http_status=0,
            ),
            _source(
                "searxng",
                http_status=503,
                error="HTTP 503: Service Unavailable",
            ),
        ]
    )
    mixed_result = adapter.parse(_request(), Path("."), mixed, "", 0)

    assert mixed_result.status == "succeeded"
    assert len(mixed_result.findings) == 3
    mixed_by_source = {f.attributes["source"]: f for f in mixed_result.findings}

    ok_finding = mixed_by_source["marginalia"]
    assert ok_finding.value == "MARGINALIA:https://example.invalid/synthetic-marginalia-one"
    assert ok_finding.record_type == "marginalia_search_result"

    skipped_finding = mixed_by_source["common-crawl-index"]
    assert skipped_finding.value == "common-crawl-index:skipped"
    assert skipped_finding.record_type is None
    assert skipped_finding.attributes["details"] == {
        "skipped": True,
        "reason": "A documented skip for this run",
    }
    assert "Skipped: A documented skip for this run" in skipped_finding.provenance.notes

    error_finding = mixed_by_source["searxng"]
    assert error_finding.value == "searxng:error"
    assert error_finding.record_type is None
    assert error_finding.attributes["details"] == {
        "error": "HTTP 503: Service Unavailable",
        "http_status": 503,
    }
    assert "Error: HTTP 503: Service Unavailable" in error_finding.provenance.notes

    for finding in mixed_result.findings:
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.WEB_SEARCH_RESULT)
    _assert_provenance_hash_invariant(mixed_result.findings)


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    reason = "A documented skip for this run"
    payload = _payload([_source("common-crawl-index", skipped=True, skip_reason=reason, http_status=0)])

    adapter = SearchEnginesAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "common-crawl-index"
    assert finding.value == "common-crawl-index:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": reason}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
    assert f"Skipped: {reason}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not a record."""
    payload = _payload(
        [_source("marginalia", http_status=429, error="HTTP 429: Too Many Requests")]
    )

    adapter = SearchEnginesAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "marginalia"
    assert finding.value == "marginalia:error"
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
    payload = _payload([_source("marginalia", data=None, raw_hash=None)])

    adapter = SearchEnginesAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = SearchEnginesAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = SearchEnginesAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = SearchEnginesAdapter()
    assert adapter.supports(SeedType.NAME)
    assert not adapter.supports(SeedType.EMAIL)
    assert not adapter.supports(SeedType.DOMAIN)
    assert not adapter.supports(SeedType.CRYPTO_ADDRESS)


def test_adapter_build_command_name():
    adapter = SearchEnginesAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["name", "test_val"]
    assert adapter.descriptor.input_types == [SeedType.NAME]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "search_engines" in registry

    descriptor = registry["search_engines"].descriptor
    assert descriptor.name == "search_engines"
    assert descriptor.input_types == [SeedType.NAME]
    assert descriptor.output_types == [EntityType.WEB_SEARCH_RESULT]
    assert descriptor.docker_image == "aletheia/search-engines:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == ["MARGINALIA_API_KEY"]
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)
    assert descriptor.upstream.endswith("docker/search_engines")


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
    assert kinds["marginalia"] == "http_api"
    assert kinds["common-crawl-index"] == "http_api"
    assert kinds["searxng"] == "self_hosted_instance"
    assert kinds["google-custom-search"] == "dropped"
    assert inventory["dropped_sub_sources"] == ["google-custom-search"]
    for entry in inventory["sub_sources"]:
        assert isinstance(entry["key_configured"], bool), entry["source"]


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
    # Every sub-source has a query function; the dropped candidate's function
    # never queries and simply reports its documented skip.
    assert callable(runner.query_searxng)
    assert callable(runner.query_google_custom_search)
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
        "marginalia": "MARGINALIA_API_URL",
        "common-crawl-index": "COMMON_CRAWL_INDEX_BASE",
    }
    for source, constant in endpoint_constants.items():
        endpoint = getattr(runner, constant)
        assert endpoint.startswith("https://"), source
        function_source = inspect.getsource(_runner_function(runner, source))
        if source == "common-crawl-index":
            # The index URL is assembled by this documented helper.
            function_source += inspect.getsource(runner._common_crawl_endpoint)
        assert constant in function_source, source
    # The Common Crawl crawl id is an explicit pinned crawl, never a wildcard.
    assert runner.COMMON_CRAWL_CRAWL_ID.startswith("CC-MAIN-")
    assert "*" not in runner.COMMON_CRAWL_CRAWL_ID
    assert runner.COMMON_CRAWL_CRAWL_ID_SOURCE == "https://commoncrawl.org/get-started"
    assert "COMMON_CRAWL_CRAWL_ID" in inspect.getsource(runner._common_crawl_endpoint)
    # The self-hosted sub-source is queried strictly over loopback, from a
    # documented endpoint, with the upstream commit pinned exactly.
    assert runner.SEARXNG_SEARCH_URL.startswith("http://127.0.0.1:")
    assert runner.SEARXNG_DOCS.startswith("https://docs.searxng.org/")
    assert runner.SEARXNG_PINNED_COMMIT == "1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4"
    assert "SEARXNG_SEARCH_URL" in inspect.getsource(runner._searxng_endpoint)
    assert "SEARXNG_PINNED_COMMIT" in inspect.getsource(runner.query_searxng)


def test_runner_skips_dropped_candidates_without_network(monkeypatch):
    runner = _load_runner()

    def _boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("a dropped candidate must never fetch anything")

    monkeypatch.setattr(runner, "_fetch_json", _boom)
    monkeypatch.setattr(runner, "_fetch_text", _boom)
    monkeypatch.setattr(runner, "_fetch_json_local", _boom)
    monkeypatch.setattr(runner, "_boot_searxng", _boom)

    gcs = runner.query_google_custom_search(FIXTURE_INPUT_VALUE)
    assert gcs.skipped is True
    assert gcs.skip_reason == UNSUPPORTED_SUB_SOURCES["google-custom-search"]


def test_runner_parses_the_documented_marginalia_shape(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv(runner.MARGINALIA_API_KEY_ENV, raising=False)
    captured = {}

    def fake_fetch_json(url, timeout=30, headers=None, max_bytes=0):
        captured["url"] = url
        captured["headers"] = headers
        return {
            "query": FIXTURE_INPUT_VALUE,
            "license": "CC-BY-NC-SA 4.0",
            "results": [
                {
                    "url": "https://example.invalid/one",
                    "title": "Example One",
                    "description": "A description",
                }
            ],
        }, 200, None

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch_json)
    result = runner.query_marginalia(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert result.http_status == 200
    # The public key is documented and is used only in the API-Key header, never
    # in the URL.
    assert captured["headers"]["API-Key"] == "public"
    assert "public" not in captured["url"]
    assert result.data["license"] == "CC-BY-NC-SA 4.0"
    assert result.data["key_source"] == "documented-public-default"
    assert result.data["records"][0]["record_id"] == "https://example.invalid/one"


def test_runner_prefers_a_configured_marginalia_key(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv(runner.MARGINALIA_API_KEY_ENV, "se_test_key")
    captured = {}

    def fake_fetch_json(url, timeout=30, headers=None, max_bytes=0):
        captured["headers"] = headers
        return {"results": [{"url": "https://example.invalid/one", "title": "t"}]}, 200, None

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch_json)
    result = runner.query_marginalia(FIXTURE_INPUT_VALUE)
    assert result.data["key_source"] == "environment"
    assert captured["headers"]["API-Key"] == "se_test_key"


def test_runner_parses_the_documented_common_crawl_jsonl_shape(monkeypatch):
    runner = _load_runner()
    captured = {}

    def fake_fetch_text(url, timeout=30, headers=None, max_bytes=0):
        captured["url"] = url
        return "\n".join(
            json.dumps(line)
            for line in [
                {
                    "urlkey": "invalid,example)/one",
                    "timestamp": "20260101000000",
                    "url": "https://example.invalid/one",
                    "mime": "text/html",
                    "status": "200",
                    "digest": "SHA1:AAAABBBB",
                    "length": "1234",
                    "offset": "0",
                    "filename": "crawl-data/x.warc.gz",
                },
                {
                    "urlkey": "invalid,example)/two",
                    "timestamp": "20260102000000",
                    "url": "https://example.invalid/two",
                    "mime": "text/html",
                    "status": "200",
                    "digest": "SHA1:CCCCDDDD",
                    "length": "5678",
                    "offset": "4321",
                    "filename": "crawl-data/y.warc.gz",
                },
            ]
        ), 200, None

    monkeypatch.setattr(runner, "_fetch_text", fake_fetch_text)
    result = runner.query_common_crawl_index(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert runner.COMMON_CRAWL_CRAWL_ID in captured["url"]
    assert "output=json" in captured["url"]
    assert "url=" in captured["url"]
    assert result.data["crawl_id"] == runner.COMMON_CRAWL_CRAWL_ID
    assert len(result.data["records"]) == 2
    assert result.data["records"][0]["url"] == "https://example.invalid/one"
    assert result.data["records"][1]["status"] == "200"


def test_runner_records_an_http_error_without_leaking_the_key(monkeypatch):
    """A failing keyed request is recorded as an error with no key in the output."""
    runner = _load_runner()
    monkeypatch.setenv(runner.MARGINALIA_API_KEY_ENV, "super-secret-key")
    monkeypatch.setattr(
        runner, "_fetch_json", lambda *a, **k: (None, 403, "HTTP 403: Forbidden")
    )
    result = runner.query_marginalia(FIXTURE_INPUT_VALUE)
    assert result.error == "HTTP 403: Forbidden"
    assert result.data is None
    assert "super-secret-key" not in json.dumps(result.to_dict())


def test_runner_reports_an_empty_result_as_no_finding(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv(runner.MARGINALIA_API_KEY_ENV, raising=False)
    monkeypatch.setattr(runner, "_fetch_json", lambda *a, **k: ({"results": []}, 200, None))
    result = runner.query_marginalia(FIXTURE_INPUT_VALUE)
    assert result.error is None
    assert result.data is None
    assert result.raw_hash is None


def test_runner_searxng_boot_failure_is_recorded(monkeypatch):
    runner = _load_runner()

    def _boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("no query may be issued when the instance is down")

    monkeypatch.setattr(runner, "_boot_searxng", lambda: (False, "boom"))
    monkeypatch.setattr(runner, "_fetch_json_local", _boom)
    result = runner.query_searxng(FIXTURE_INPUT_VALUE)
    assert result.skipped is False
    assert result.data is None
    assert result.error is not None and "boom" in result.error


def test_runner_parses_the_documented_searxng_shape(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_boot_searxng", lambda: (True, None))
    captured = {}

    def fake_fetch_local(url, timeout=None):
        captured["url"] = url
        return {
            "query": FIXTURE_INPUT_VALUE,
            "number_of_results": 1,
            "results": [
                {
                    "url": "https://example.invalid/one",
                    "title": "One",
                    "content": "A description",
                    "engine": "duckduckgo",
                }
            ],
            "unresponsive_engines": [],
        }, 200, None

    monkeypatch.setattr(runner, "_fetch_json_local", fake_fetch_local)
    result = runner.query_searxng(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert result.http_status == 200
    assert captured["url"] == runner.SEARXNG_SEARCH_URL + "?" + urllib.parse.urlencode(
        {"q": FIXTURE_INPUT_VALUE, "format": "json"}
    )
    assert result.data["instance"] == runner.SEARXNG_BASE_URL
    assert result.data["pinned_commit"] == runner.SEARXNG_PINNED_COMMIT
    assert result.data["engines_config"] == list(runner.SEARXNG_ENGINES)
    assert result.data["engines_used"] == ["duckduckgo"]
    assert result.data["records"][0]["record_id"] == "https://example.invalid/one"
    assert result.data["records"][0]["snippet"] == "A description"
    assert result.data["records"][0]["engine"] == "duckduckgo"


def test_runner_searxng_no_results_with_unresponsive_engines_is_an_error(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_boot_searxng", lambda: (True, None))
    monkeypatch.setattr(
        runner,
        "_fetch_json_local",
        lambda *a, **k: (
            {"results": [], "unresponsive_engines": [["duckduckgo", "HTTP timeout"]]},
            200,
            None,
        ),
    )
    result = runner.query_searxng(FIXTURE_INPUT_VALUE)
    assert result.data is None
    assert result.error is not None and "duckduckgo" in result.error


def test_runner_searxng_empty_result_is_no_finding(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_boot_searxng", lambda: (True, None))
    monkeypatch.setattr(runner, "_fetch_json_local", lambda *a, **k: ({"results": []}, 200, None))
    result = runner.query_searxng(FIXTURE_INPUT_VALUE)
    assert result.error is None
    assert result.data is None
    assert result.raw_hash is None


def test_runner_searxng_settings_follow_the_documented_mechanisms():
    runner = _load_runner()
    settings = runner._searxng_settings_dict(None)
    assert settings["use_default_settings"] == {"engines": {"keep_only": list(runner.SEARXNG_ENGINES)}}
    assert settings["search"]["formats"] == ["html", "json"]
    assert settings["server"]["bind_address"] == "127.0.0.1"
    assert settings["server"]["limiter"] is False
    assert {entry["name"] for entry in settings["engines"]} == set(runner.SEARXNG_ENGINES)
    for entry in settings["engines"]:
        assert entry["disabled"] is False
    assert "proxies" not in settings["outgoing"]

    proxied = runner._searxng_settings_dict("http://proxy.example:8899")
    assert proxied["outgoing"]["proxies"] == {"all://": ["http://proxy.example:8899"]}


def test_runner_searxng_settings_file_is_written_as_parseable_json(tmp_path):
    runner = _load_runner()
    path = tmp_path / "settings.yml"
    runner._write_searxng_settings(path, None)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["server"]["bind_address"] == "127.0.0.1"
    assert parsed["search"]["formats"] == ["html", "json"]


def test_runner_selftest_mode_reports_the_pinned_commit(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_boot_searxng", lambda: (True, None))
    monkeypatch.setattr(
        runner,
        "_fetch_json_local",
        lambda *a, **k: (
            {"results": [], "unresponsive_engines": [["duckduckgo", "unreachable"]]},
            200,
            None,
        ),
    )
    old_argv = sys.argv
    old_stdout = sys.stdout
    try:
        sys.argv = ["runner.py", "--selftest-searxng"]
        sys.stdout = io.StringIO()
        assert runner.main() == 0
        report = json.loads(sys.stdout.getvalue())
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
    assert report["searxng_selftest"] == "ok"
    assert report["pinned_commit"] == runner.SEARXNG_PINNED_COMMIT
    assert report["http_status"] == 200
    assert report["results_returned"] == 0


def test_runner_selftest_mode_fails_when_the_boot_fails(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_boot_searxng", lambda: (False, "boom"))
    old_argv = sys.argv
    old_stdout = sys.stdout
    try:
        sys.argv = ["runner.py", "--selftest-searxng"]
        sys.stdout = io.StringIO()
        assert runner.main() == 1
        report = json.loads(sys.stdout.getvalue())
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
    assert report["searxng_selftest"] == "failed"
    assert "boom" in report["error"]
