"""Parser + fixture tests for the academic_search batch adapter."""

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

from aletheia.adapters.academic_search import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    AcademicSearchAdapter,
    AcademicSearchFinding,
    _extract_authors,
    _extract_details,
    _extract_doi,
    _extract_record_type,
    _extract_subject,
    _extract_title,
    _extract_year,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIXTURE_PATH = "tests/fixtures/academic_search.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = (
    "openalex",
    "crossref",
    "semantic-scholar",
    "arxiv",
    "core",
    "openaire",
)

# unpaywall is queried only when the input itself is a DOI (its documented
# title search was retired on 18 September 2026 and now returns 410 Gone; the
# DOI lookup requires a contact email). Name-based inputs therefore appear in
# the fixture as a skip carrying this exact reason and are never queried.
SKIP_REASONS = {
    "unpaywall": (
        "Unpaywall documents no title, keyword or author search: the documented title search "
        "(GET /v2/search?query=...) was retired on 18 September 2026 and now returns 410 Gone, and a "
        "name-based input is not a DOI. Its only live endpoint is the DOI lookup (GET /v2/:doi, which "
        "requires a contact-email parameter), so no documented contract exists for this input. See "
        "docker/academic_search/RATE_LIMITS.md."
    ),
}

# The single published search endpoint each implemented sub-source calls. The
# runner resolves every URL from a module constant, so the fixture and the tests
# can check the exact endpoint instead of trusting a literal in a function body.
URL_CONSTANTS = {
    "openalex": "OPENALEX_ENDPOINT",
    "crossref": "CROSSREF_ENDPOINT",
    "semantic-scholar": "SEMANTIC_SCHOLAR_ENDPOINT",
    "arxiv": "ARXIV_ENDPOINT",
    "core": "CORE_ENDPOINT",
    "openaire": "OPENAIR_E_ENDPOINT",
}

DOCS_CONSTANTS = {
    "openalex": "OPENALEX_DOCS",
    "crossref": "CROSSREF_DOCS",
    "semantic-scholar": "SEMANTIC_SCHOLAR_DOCS",
    "arxiv": "ARXIV_DOCS",
    "core": "CORE_DOCS",
    "openaire": "OPENAIR_E_DOCS",
}

# The verbatim search parameter each provider documents, and nothing else.
DOCUMENTED_PARAMETER = {
    "openalex": "search",
    "crossref": "query.bibliographic",
    "semantic-scholar": "query",
    "arxiv": "search_query",
    "core": "q",
    "openaire": "search",
}


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "academic_search_runner",
        ROOT / "docker" / "academic_search" / "runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_function(module, source: str):
    return getattr(module, "query_" + source.replace("-", "_"))


# -- subject extraction --------------------------------------------------------


def test_extract_subject_openalex():
    data = {"records": [{"record_id": "W2144093431", "title": "A Synthetic Study"}]}
    assert _extract_subject(data, "openalex") == "OPENALEX:W2144093431:A Synthetic Study"


def test_extract_subject_crossref():
    data = {"records": [{"record_id": "10.9999/x", "title": "Synthetic Crossref Record"}]}
    assert _extract_subject(data, "crossref") == "CROSSREF:10.9999/x:Synthetic Crossref Record"


def test_extract_subject_semantic_scholar():
    data = {"records": [{"record_id": "abcdef", "title": "Synthetic Paper"}]}
    assert _extract_subject(data, "semantic-scholar") == "SEMANTIC_SCHOLAR:abcdef:Synthetic Paper"


def test_extract_subject_arxiv():
    data = {"records": [{"record_id": "2601.09999v1", "title": "Synthetic Preprint"}]}
    assert _extract_subject(data, "arxiv") == "ARXIV:2601.09999v1:Synthetic Preprint"


def test_extract_subject_core():
    data = {"records": [{"record_id": "99999999", "title": "Synthetic Deposit"}]}
    assert _extract_subject(data, "core") == "CORE:99999999:Synthetic Deposit"


def test_extract_subject_openaire():
    data = {"records": [{"record_id": "doi_dedup::10.9999/x", "title": "Synthetic Product"}]}
    assert _extract_subject(data, "openaire") == "OPENAIRE:doi_dedup::10.9999/x:Synthetic Product"


def test_extract_subject_without_a_record_falls_back_to_source():
    """A payload with no record never claims an academic identifier."""
    for source in SUPPORTED_SOURCES:
        assert _extract_subject({"records": [], "record_count": 0}, source) == source


# -- record field extraction ---------------------------------------------------


def test_extract_record_type():
    cases = [
        ("openalex", "openalex_work"),
        ("crossref", "crossref_work"),
        ("semantic-scholar", "semantic_scholar_paper"),
        ("arxiv", "arxiv_preprint"),
        ("core", "core_work"),
        ("openaire", "openaire_research_product"),
        ("unpaywall", "unpaywall_doi_record"),
        ("unknown-source", None),
    ]
    for source, expected in cases:
        result = _extract_record_type({"dummy": True}, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


def test_extract_record_fields_from_the_openalex_payload():
    data = {
        "records": [
            {
                "record_id": "W2144093431",
                "title": "Acme Holdings and the Governance of Synthetic Data",
                "doi": "10.9999/aletheia.synthetic.0001",
                "authors": ["Jane Acme", "John Acme"],
                "year": 2021,
                "venue": "Journal of Synthetic Research",
            }
        ]
    }
    assert _extract_title(data, "openalex") == "Acme Holdings and the Governance of Synthetic Data"
    assert _extract_doi(data, "openalex") == "10.9999/aletheia.synthetic.0001"
    assert _extract_authors(data, "openalex") == ["Jane Acme", "John Acme"]
    assert _extract_year(data, "openalex") == 2021


def test_extract_record_fields_without_a_record_are_none():
    for source in SUPPORTED_SOURCES:
        empty = {"records": [], "record_count": 0}
        assert _extract_title(empty, source) is None
        assert _extract_doi(empty, source) is None
        assert _extract_authors(empty, source) is None
        assert _extract_year(empty, source) is None


# -- details extraction --------------------------------------------------------


def test_extract_details_openalex():
    data = {
        "endpoint": "https://api.openalex.org/works",
        "api_documentation": "https://help.openalex.org/api/searching/",
        "record_count": 38729292,
        "truncated": False,
        "records": [
            {
                "record_id": "W2144093431",
                "title": "Acme Holdings and the Governance of Synthetic Data",
                "doi": "10.9999/aletheia.synthetic.0001",
                "authors": ["Jane Acme"],
                "year": 2021,
                "venue": "Journal of Synthetic Research",
                "type": "article",
                "cited_by_count": 12,
                "publication_date": "2021-05-04",
                "is_oa": True,
            }
        ],
    }
    result = _extract_details(data, "openalex")
    assert result["record_id"] == "W2144093431"
    assert result["cited_by_count"] == 12
    assert result["publication_date"] == "2021-05-04"
    assert result["is_oa"] is True
    assert result["record_count"] == 38729292
    assert result["truncated"] is False
    assert result["endpoint"] == "https://api.openalex.org/works"


def test_extract_details_crossref():
    data = {
        "endpoint": "https://api.crossref.org/works",
        "record_count": 1,
        "records": [
            {
                "record_id": "10.9999/aletheia.synthetic.0002",
                "title": "A Synthetic Survey of Acme Holdings Disclosure Practice",
                "doi": "10.9999/aletheia.synthetic.0002",
                "authors": ["Jane Acme"],
                "year": 2019,
                "venue": "Synthetic Review of Accounting",
                "type": "journal-article",
                "publisher": "Synthetic Press",
                "issued": "2019",
                "member": "9999",
            }
        ],
    }
    result = _extract_details(data, "crossref")
    assert result["publisher"] == "Synthetic Press"
    assert result["container_title"] == "Synthetic Review of Accounting"
    assert result["issued"] == "2019"
    assert result["member"] == "9999"


def test_extract_details_arxiv():
    data = {
        "endpoint": "http://export.arxiv.org/api/query",
        "record_count": 1,
        "records": [
            {
                "record_id": "2601.09999v1",
                "title": "Synthetic Preprint on Acme Holdings Entity Resolution",
                "published": "2026-01-14T00:00:00Z",
                "updated": "2026-01-14T00:00:00Z",
                "primary_category": "cs.DL",
                "comment": "12 pages, synthetic fixture entry",
            }
        ],
    }
    result = _extract_details(data, "arxiv")
    assert result["primary_category"] == "cs.DL"
    assert result["published"] == "2026-01-14T00:00:00Z"
    assert result["comment"] == "12 pages, synthetic fixture entry"


def test_extract_details_openaire():
    data = {
        "endpoint": "https://api.openaire.eu/graph/v3/research-products",
        "record_count": 1,
        "records": [
            {
                "record_id": "doi_dedup::10.9999/aletheia.synthetic.0005",
                "title": "Acme Holdings Research Products in the OpenAIRE Graph",
                "doi": "10.9999/aletheia.synthetic.0005",
                "authors": ["Jane Acme"],
                "year": 2023,
                "venue": "Synthetic Open Science Journal",
                "type": "publication",
                "publisher": "Synthetic Open Science Press",
                "publication_date": "2023-03-02",
            }
        ],
    }
    result = _extract_details(data, "openaire")
    assert result["publisher"] == "Synthetic Open Science Press"
    assert result["publication_date"] == "2023-03-02"
    assert result["type"] == "publication"


def test_extract_details_without_a_record_is_none():
    for source in SUPPORTED_SOURCES:
        assert _extract_details({"records": []}, source) is None


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = AcademicSearchFinding(
        subject="OPENALEX:W2144093431:A Synthetic Study",
        source="openalex",
        record_type="openalex_work",
        title="A Synthetic Study",
        doi="10.9999/aletheia.synthetic.0001",
        authors=["Jane Acme"],
        year=2021,
        venue="Journal of Synthetic Research",
        identifier="W2144093431",
        url="https://openalex.org/W2144093431",
        details={"record_id": "W2144093431"},
        raw_evidence={"records": [{"record_id": "W2144093431"}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:openalex",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from openalex"],
        ),
    )
    assert finding.entity_type == EntityType.ACADEMIC_RECORD
    assert finding.entity_type.value == "academic_record"
    assert finding.attributes["source"] == "openalex"
    assert finding.attributes["doi"] == "10.9999/aletheia.synthetic.0001"
    assert finding.subject == "OPENALEX:W2144093431:A Synthetic Study"
    assert finding.title == "A Synthetic Study"
    assert finding.doi == "10.9999/aletheia.synthetic.0001"


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    runner = _load_runner()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 7
    assert set(sources) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    assert set(UNSUPPORTED_SUB_SOURCES) == set(SKIP_REASONS)
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
        # The recorded endpoint and documentation URL are the ones the runner
        # actually uses, so a fixture can never point at an endpoint the runner
        # does not call.
        assert entry["data"]["endpoint"] == getattr(runner, URL_CONSTANTS[source]), source
        assert entry["data"]["api_documentation"] == getattr(runner, DOCS_CONSTANTS[source]), source

    # The dropped sub-source is present exactly once, as an auditable skip.
    skipped = by_source["unpaywall"]
    assert skipped["skipped"] is True
    assert skipped["data"] is None
    assert skipped["raw_hash"] is None
    assert skipped["skip_reason"] == SKIP_REASONS["unpaywall"]


def test_fixture_uses_only_synthetic_values():
    """The fixture is synthetic and must not read as captured live output."""
    fixture = load_fixture()
    for entry in fixture["sources"]:
        if entry["skipped"]:
            continue
        for record in entry["data"]["records"]:
            text = json.dumps(record).casefold()
            assert "synthetic" in text or "acme holdings" in text, entry["source"]
            assert record["doi"].startswith("10.9999/") or record["doi"] == "", entry["source"]


# -- run result parsing --------------------------------------------------------


def _request(value: str = "Acme Holdings") -> AdapterRunRequest:
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
            "input_value": "Acme Holdings",
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


@parser_test("academic_search")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = AcademicSearchAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 7

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES) | {"unpaywall"}

    openalex = by_source["openalex"]
    assert openalex.value == (
        "OPENALEX:W2144093431:Acme Holdings and the Governance of Synthetic Data: A Reproducible Study"
    )
    assert openalex.subject == openalex.value
    assert openalex.record_type == "openalex_work"
    assert openalex.title == "Acme Holdings and the Governance of Synthetic Data: A Reproducible Study"
    assert openalex.doi == "10.9999/aletheia.synthetic.0001"
    assert openalex.attributes["authors"] == ["Jane Acme", "John Acme"]
    assert openalex.attributes["year"] == 2021
    assert openalex.attributes["venue"] == "Journal of Synthetic Research"
    assert openalex.attributes["details"]["cited_by_count"] == 12
    assert openalex.attributes["details"]["is_oa"] is True

    crossref = by_source["crossref"]
    assert crossref.value.startswith("CROSSREF:10.9999/aletheia.synthetic.0002:")
    assert crossref.record_type == "crossref_work"
    assert crossref.attributes["details"]["publisher"] == "Synthetic Press"

    semantic_scholar = by_source["semantic-scholar"]
    assert semantic_scholar.record_type == "semantic_scholar_paper"
    assert semantic_scholar.doi == "10.9999/aletheia.synthetic.0003"
    assert semantic_scholar.attributes["details"]["citation_count"] == 4

    arxiv = by_source["arxiv"]
    assert arxiv.value == "ARXIV:2601.09999v1:Synthetic Preprint on Acme Holdings Entity Resolution"
    assert arxiv.record_type == "arxiv_preprint"
    assert arxiv.attributes["year"] == 2026
    assert arxiv.attributes["venue"] == "arXiv"
    assert arxiv.attributes["details"]["primary_category"] == "cs.DL"

    core = by_source["core"]
    assert core.record_type == "core_work"
    assert core.attributes["details"]["download_url"] == "https://core.ac.uk/download/99999999.pdf"

    openaire = by_source["openaire"]
    assert openaire.record_type == "openaire_research_product"
    assert openaire.attributes["details"]["publisher"] == "Synthetic Open Science Press"

    for finding in result.findings:
        assert isinstance(finding, AcademicSearchFinding)
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.ACADEMIC_RECORD)
        assert finding.provenance.tool == "academic_search"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80

    # The dropped sub-source must appear as a skip with its documented reason and
    # must never be reported as a record.
    skipped_finding = by_source["unpaywall"]
    assert skipped_finding.value == "unpaywall:skipped"
    assert skipped_finding.record_type is None
    assert skipped_finding.title is None
    assert skipped_finding.attributes["details"] == {
        "skipped": True,
        "reason": SKIP_REASONS["unpaywall"],
    }
    assert f"Skipped: {SKIP_REASONS['unpaywall']}" in skipped_finding.provenance.notes

    _assert_provenance_hash_invariant(result.findings)

    # A mixed runner payload must yield a real finding, a skip finding and an
    # error finding, each with the same provenance hash invariant.
    mixed = _payload(
        [
            _source("openalex", data=fixture["sources"][0]["data"],
                    raw_hash=fixture["sources"][0]["raw_hash"]),
            _source(
                "core",
                skipped=True,
                skip_reason="CORE_API_KEY was rejected for this run",
                http_status=0,
            ),
            _source(
                "openaire",
                http_status=503,
                error="HTTP 503: Service Unavailable",
            ),
        ]
    )
    mixed_result = adapter.parse(_request(), Path("."), mixed, "", 0)

    assert mixed_result.status == "succeeded"
    assert len(mixed_result.findings) == 3
    mixed_by_source = {f.attributes["source"]: f for f in mixed_result.findings}

    ok_finding = mixed_by_source["openalex"]
    assert ok_finding.record_type == "openalex_work"

    skipped = mixed_by_source["core"]
    assert skipped.value == "core:skipped"
    assert skipped.record_type is None
    assert skipped.attributes["details"] == {
        "skipped": True,
        "reason": "CORE_API_KEY was rejected for this run",
    }
    assert "Skipped: CORE_API_KEY was rejected for this run" in skipped.provenance.notes

    errored = mixed_by_source["openaire"]
    assert errored.value == "openaire:error"
    assert errored.record_type is None
    assert errored.attributes["details"] == {
        "error": "HTTP 503: Service Unavailable",
        "http_status": 503,
    }
    assert "Error: HTTP 503: Service Unavailable" in errored.provenance.notes

    for finding in mixed_result.findings:
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.ACADEMIC_RECORD)
    _assert_provenance_hash_invariant(mixed_result.findings)


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    reason = SKIP_REASONS["unpaywall"]
    payload = _payload([_source("unpaywall", skipped=True, skip_reason=reason, http_status=0)])

    adapter = AcademicSearchAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "unpaywall"
    assert finding.value == "unpaywall:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": reason}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
    assert f"Skipped: {reason}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not a record."""
    payload = _payload(
        [_source("semantic-scholar", http_status=429, error="HTTP 429: Too Many Requests")]
    )

    adapter = AcademicSearchAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "semantic-scholar"
    assert finding.value == "semantic-scholar:error"
    assert finding.attributes["details"] == {
        "error": "HTTP 429: Too Many Requests",
        "http_status": 429,
    }
    assert "Error: HTTP 429: Too Many Requests" in finding.provenance.notes

    # A sub-source error must not be reported as a record.
    assert finding.record_type is None
    assert finding.attributes.get("raw_evidence") == {
        "error": "HTTP 429: Too Many Requests",
        "http_status": 429,
    }
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
        json.dumps(finding.attributes["raw_evidence"], sort_keys=True).encode()
    ).hexdigest()


def test_parse_no_match_produces_no_finding():
    """A source with no result must not be reported as a record."""
    payload = _payload([_source("crossref", data=None, raw_hash=None)])

    adapter = AcademicSearchAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = AcademicSearchAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = AcademicSearchAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = AcademicSearchAdapter()
    assert adapter.supports(SeedType.NAME)
    assert adapter.supports(SeedType.COMPANY_NAME)
    assert adapter.supports(SeedType.PERSON_NAME)
    assert not adapter.supports(SeedType.EMAIL)


def test_adapter_input_types():
    adapter = AcademicSearchAdapter()
    type_map = {
        SeedType.NAME: "name",
        SeedType.COMPANY_NAME: "company_name",
        SeedType.PERSON_NAME: "person_name",
    }
    for seed_type, expected in type_map.items():
        seed_obj = type("Seed", (), {"type": seed_type, "value": "test_val"})()
        req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
        cmd = adapter.build_command(req, None)
        assert cmd[0] == expected, f"{seed_type}: expected {expected}, got {cmd[0]}"
    assert adapter.descriptor.input_types == [
        SeedType.NAME,
        SeedType.COMPANY_NAME,
        SeedType.PERSON_NAME,
    ]


def test_adapter_build_command_name():
    adapter = AcademicSearchAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["name", "test_val"]


def test_adapter_build_command_company_name():
    adapter = AcademicSearchAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.COMPANY_NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["company_name", "test_val"]


def test_adapter_build_command_person_name():
    adapter = AcademicSearchAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.PERSON_NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["person_name", "test_val"]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "academic_search" in registry

    descriptor = registry["academic_search"].descriptor
    assert descriptor.name == "academic_search"
    assert descriptor.input_types == [SeedType.NAME, SeedType.COMPANY_NAME, SeedType.PERSON_NAME]
    assert descriptor.output_types == [EntityType.ACADEMIC_RECORD]
    assert descriptor.docker_image == "aletheia/academic-search:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == [
        "OPENALEX_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
        "CORE_API_KEY",
        "CROSSREF_MAILTO",
        "UNPAYWALL_EMAIL",
    ]
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)
    assert descriptor.upstream.endswith("docker/academic_search")


def test_adapter_documents_the_unpaywall_doi_only_route():
    """Non-DOI inputs stay an auditable, reasoned skip on a DOI-only route."""
    assert set(UNSUPPORTED_SUB_SOURCES) == {"unpaywall"}
    assert not set(UNSUPPORTED_SUB_SOURCES) & set(SUPPORTED_SUB_SOURCES)
    reason = UNSUPPORTED_SUB_SOURCES["unpaywall"]
    assert "410 Gone" in reason
    assert "retired" in reason
    assert "not a DOI" in reason

    runner_source = (ROOT / "docker" / "academic_search" / "runner.py").read_text(encoding="utf-8")
    assert 'UNSUPPORTED_SUB_SOURCES: dict[str, str] = {' in runner_source
    function_source = inspect.getsource(_runner_function(_load_runner(), "unpaywall"))
    assert "http://" not in function_source
    assert "https://" not in function_source


# -- docker runner -------------------------------------------------------------


def test_runner_health_check():
    runner = _load_runner()
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


def test_runner_rejects_invalid_arguments():
    runner = _load_runner()
    old_argv = sys.argv
    old_stderr = sys.stderr
    try:
        sys.stderr = io.StringIO()
        sys.argv = ["runner.py"]
        assert runner.main() == 2
        sys.argv = ["runner.py", "invalid_type", "Acme Holdings"]
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


def test_runner_defines_no_endpoint_for_unsupported_sources():
    """Non-matching inputs are auditable skips with no URL, never a guessed call."""
    runner = _load_runner()
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES
    for source, reason in UNSUPPORTED_SUB_SOURCES.items():
        assert isinstance(reason, str) and reason.strip()
        function_source = inspect.getsource(_runner_function(runner, source))
        assert "http://" not in function_source
        assert "https://" not in function_source
        result = _runner_function(runner, source)("Acme Holdings")
        assert result.skipped is True
        assert result.skip_reason == reason
        assert result.data is None
        assert result.raw_hash is None


def test_runner_extracts_dois_from_inputs():
    """Only DOI-shaped inputs reach the Unpaywall DOI endpoint."""
    runner = _load_runner()
    assert runner._doi_from_query("10.1038/nature12373") == "10.1038/nature12373"
    assert runner._doi_from_query("https://doi.org/10.1038/nature12373") == "10.1038/nature12373"
    assert runner._doi_from_query("doi:10.1038/nature12373") == "10.1038/nature12373"
    assert runner._doi_from_query("Acme Holdings") is None
    assert runner._doi_from_query("10.1038") is None


def test_runner_unpaywall_queries_the_doi_endpoint(monkeypatch):
    runner = _load_runner()
    captured: dict = {}

    def fake_fetch_json(url, params=None, headers=None):
        captured["url"] = url
        captured["params"] = params
        return (
            {
                "doi": "10.1038/nature12373",
                "title": "Synthetic Open-Access Paper",
                "year": 2013,
                "journal_name": "Nature",
                "is_oa": True,
                "oa_status": "gold",
                "z_authors": [{"given": "Jane", "family": "Acme"}],
                "best_oa_location": {"url": "https://example.org/oa.pdf"},
            },
            200,
            None,
        )

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch_json)
    monkeypatch.setenv("UNPAYWALL_EMAIL", "osint@example.org")
    result = runner.query_unpaywall("10.1038/nature12373")

    assert result.skipped is False
    assert result.error is None
    assert result.http_status == 200
    assert captured["url"] == "https://api.unpaywall.org/v2/10.1038/nature12373"
    assert captured["params"] == {"email": "osint@example.org"}
    record = result.data["records"][0]
    assert record["record_id"] == "10.1038/nature12373"
    assert record["title"] == "Synthetic Open-Access Paper"
    assert record["venue"] == "Nature"
    assert record["authors"] == ["Jane Acme"]
    assert record["url"] == "https://example.org/oa.pdf"
    assert result.data["raw"]["doi"] == "10.1038/nature12373"


def test_runner_unpaywall_skips_without_the_contact_email(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    result = runner.query_unpaywall("10.1038/nature12373")
    assert result.skipped is True
    assert result.skip_reason == runner.UNPAYWALL_EMAIL_MISSING_REASON


def test_parse_live_unpaywall_doi_record():
    """The DOI-path payload parses to a normal academic finding."""
    data = {
        "api_source": "Unpaywall REST API v2 (DOI lookup)",
        "api_documentation": "https://unpaywall.org/products/api",
        "endpoint": "https://api.unpaywall.org/v2/:doi",
        "query": "10.1038/nature12373",
        "record_count": 1,
        "truncated": False,
        "records": [
            {
                "record_id": "10.1038/nature12373",
                "doi": "10.1038/nature12373",
                "title": "Synthetic Open-Access Paper",
                "year": 2013,
                "venue": "Nature",
                "authors": ["Jane Acme"],
                "url": "https://example.org/oa.pdf",
            }
        ],
    }
    payload = _payload([_source("unpaywall", http_status=200, data=data)])

    adapter = AcademicSearchAdapter()
    result = adapter.parse(_request("10.1038/nature12373"), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "unpaywall"
    assert finding.record_type == "unpaywall_doi_record"
    assert finding.doi == "10.1038/nature12373"
    assert finding.value == "UNPAYWALL:10.1038/nature12373:Synthetic Open-Access Paper"
    assert finding.attributes["details"]["record_count"] == 1
    assert finding.attributes["details"]["venue"] == "Nature"
    _assert_provenance_hash_invariant(result.findings)


def test_runner_supported_sources_cite_a_documented_endpoint():
    """Every implemented sub-source queries one documented search endpoint."""
    runner = _load_runner()
    for source in SUPPORTED_SUB_SOURCES:
        url = getattr(runner, URL_CONSTANTS[source])
        docs = getattr(runner, DOCS_CONSTANTS[source])
        assert url.startswith("http://") or url.startswith("https://"), source
        assert docs.startswith("https://"), source
        function_source = inspect.getsource(_runner_function(runner, source))
        assert URL_CONSTANTS[source] in function_source, source
        assert DOCS_CONSTANTS[source] in function_source, source


def test_runner_sends_only_the_documented_search_parameter(monkeypatch):
    """Each query sends the verbatim parameter its provider documents."""
    runner = _load_runner()
    captured: dict[str, dict] = {}

    def fake_json(url, params=None, headers=None):
        captured[url] = dict(params or {})
        return {}, 200, None

    def fake_bytes(url, params=None, headers=None, timeout=45, max_bytes=0):
        captured[url] = dict(params or {})
        return b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>", 200, None

    monkeypatch.setattr(runner, "_fetch_json", fake_json)
    monkeypatch.setattr(runner, "_fetch_bytes", fake_bytes)

    for source in SUPPORTED_SOURCES:
        captured.clear()
        _runner_function(runner, source)("Acme Holdings")
        endpoint = getattr(runner, URL_CONSTANTS[source])
        assert endpoint in captured, source
        params = captured[endpoint]
        assert DOCUMENTED_PARAMETER[source] in params, source
        assert params[DOCUMENTED_PARAMETER[source]] in (
            "Acme Holdings",
            "all:Acme Holdings",
        ), source


# -- runner parsing against the documented response shapes ---------------------
#
# The payloads below are minimal synthetic documents that follow the response
# structure of the real published documents (captured while writing the runner):
# OpenAlex meta/results, the Crossref message/items envelope, the Semantic
# Scholar total/offset/data envelope, arXiv Atom XML with arxiv-namespaced
# extension elements, the CORE results array and the OpenAIRE header/results
# envelope. No network is used: the fetch helpers are replaced.

OPENALEX_PAYLOAD = {
    "meta": {"count": 38729292, "page": 1, "per_page": 2},
    "results": [
        {
            "id": "https://openalex.org/W2144093431",
            "doi": "https://doi.org/10.9999/aletheia.synthetic.0001",
            "title": "Acme Holdings and the Governance of Synthetic Data",
            "display_name": "Acme Holdings and the Governance of Synthetic Data",
            "publication_year": 2021,
            "publication_date": "2021-05-04",
            "type": "article",
            "cited_by_count": 12,
            "open_access": {"is_oa": True},
            "authorships": [
                {"author": {"display_name": "Jane Acme"}},
                {"author": {"display_name": "John Acme"}},
            ],
            "primary_location": {"source": {"display_name": "Journal of Synthetic Research"}},
        }
    ],
}

CROSSREF_PAYLOAD = {
    "status": "ok",
    "message-type": "work-list",
    "message": {
        "total-results": 763868,
        "items": [
            {
                "DOI": "10.9999/aletheia.synthetic.0002",
                "title": ["A Synthetic Survey of Acme Holdings Disclosure Practice"],
                "author": [{"given": "Jane", "family": "Acme"}],
                "issued": {"date-parts": [[2019]]},
                "container-title": ["Synthetic Review of Accounting"],
                "publisher": "Synthetic Press",
                "type": "journal-article",
                "URL": "https://doi.org/10.9999/aletheia.synthetic.0002",
                "member": "9999",
            }
        ],
    },
}

SEMANTIC_SCHOLAR_PAYLOAD = {
    "total": 639637,
    "offset": 0,
    "data": [
        {
            "paperId": "abcdef1234567890abcdef1234567890abcdef12",
            "title": "Acme Holdings: A Synthetic Case Study in Citation Networks",
            "year": 2022,
            "venue": "Proceedings of the Synthetic Conference",
            "publicationDate": "2022-08-15",
            "citationCount": 4,
            "url": "https://www.semanticscholar.org/paper/abcdef1234567890abcdef1234567890abcdef12",
            "externalIds": {"DOI": "10.9999/aletheia.synthetic.0003", "CorpusId": 99999999},
            "authors": [{"authorId": "1", "name": "Jane Acme"}, {"authorId": "2", "name": "R. Synthetic"}],
        }
    ],
}

ARXIV_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>arXiv Query: search_query=all:Acme Holdings</title>
  <opensearch:totalResults>3</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2601.09999v1</id>
    <updated>2026-01-14T00:00:00Z</updated>
    <published>2026-01-14T00:00:00Z</published>
    <title>Synthetic Preprint on Acme Holdings
  Entity Resolution</title>
    <summary>Synthetic abstract text.</summary>
    <author><name>Jane Acme</name></author>
    <arxiv:primary_category term="cs.DL"/>
    <arxiv:comment>12 pages, synthetic fixture entry</arxiv:comment>
    <link href="https://arxiv.org/abs/2601.09999v1" rel="alternate" type="text/html"/>
  </entry>
</feed>
"""

CORE_PAYLOAD = {
    "totalHits": 1234,
    "results": [
        {
            "id": 99999999,
            "doi": "10.9999/aletheia.synthetic.0004",
            "title": "Open Access Outputs of Acme Holdings: A Synthetic Deposit Record",
            "yearPublished": 2020,
            "publisher": "Synthetic Repository Press",
            "documentType": "research",
            "downloadUrl": "https://core.ac.uk/download/99999999.pdf",
            "arxivId": "",
            "authors": [{"name": "Jane Acme"}, {"name": "P. Synthetic"}],
        }
    ],
}

OPENAIR_E_PAYLOAD = {
    "header": {"numFound": 7685270, "page": 1, "pageSize": 2},
    "results": [
        {
            "id": "doi_dedup::10.9999/aletheia.synthetic.0005",
            "mainTitle": "Acme Holdings Research Products in the OpenAIRE Graph",
            "publicationDate": "2023-03-02",
            "type": "publication",
            "publisher": {"name": "Synthetic Open Science Press"},
            "authors": [{"fullName": "Jane Acme"}],
            "pids": [{"scheme": "doi", "value": "10.9999/aletheia.synthetic.0005"}],
            "container": {"name": "Synthetic Open Science Journal"},
        }
    ],
}


def _runner_with_json(monkeypatch, payload):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_fetch_json", lambda url, params=None, headers=None: (payload, 200, None))
    return runner


def _runner_with_body(monkeypatch, body: bytes):
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_fetch_bytes",
        lambda url, params=None, headers=None, timeout=45, max_bytes=0: (body, 200, None),
    )
    return runner


def test_runner_parses_the_openalex_shape(monkeypatch):
    runner = _runner_with_json(monkeypatch, OPENALEX_PAYLOAD)
    result = runner.query_openalex("Acme Holdings")

    assert result.error is None
    assert result.http_status == 200
    data = result.data
    assert data["endpoint"] == runner.OPENALEX_ENDPOINT
    assert data["record_count"] == 38729292
    record = data["records"][0]
    assert record["record_id"] == "W2144093431"
    assert record["doi"] == "10.9999/aletheia.synthetic.0001"
    assert record["authors"] == ["Jane Acme", "John Acme"]
    assert record["venue"] == "Journal of Synthetic Research"
    assert record["is_oa"] is True


def test_runner_parses_the_crossref_shape(monkeypatch):
    runner = _runner_with_json(monkeypatch, CROSSREF_PAYLOAD)
    result = runner.query_crossref("Acme Holdings")

    assert result.error is None
    data = result.data
    assert data["record_count"] == 763868
    record = data["records"][0]
    assert record["record_id"] == "10.9999/aletheia.synthetic.0002"
    assert record["authors"] == ["Jane Acme"]
    assert record["year"] == 2019
    assert record["venue"] == "Synthetic Review of Accounting"


def test_runner_parses_the_semantic_scholar_shape(monkeypatch):
    runner = _runner_with_json(monkeypatch, SEMANTIC_SCHOLAR_PAYLOAD)
    result = runner.query_semantic_scholar("Acme Holdings")

    assert result.error is None
    data = result.data
    assert data["record_count"] == 639637
    record = data["records"][0]
    assert record["record_id"] == "abcdef1234567890abcdef1234567890abcdef12"
    assert record["doi"] == "10.9999/aletheia.synthetic.0003"
    assert record["venue"] == "Proceedings of the Synthetic Conference"
    assert record["citation_count"] == 4


def test_runner_parses_the_arxiv_atom_shape(monkeypatch):
    runner = _runner_with_body(monkeypatch, ARXIV_ATOM)
    result = runner.query_arxiv("Acme Holdings")

    assert result.error is None
    data = result.data
    assert data["record_count"] == 3
    record = data["records"][0]
    assert record["record_id"] == "2601.09999v1"
    assert record["title"] == "Synthetic Preprint on Acme Holdings Entity Resolution"
    assert record["authors"] == ["Jane Acme"]
    assert record["year"] == 2026
    assert record["primary_category"] == "cs.DL"
    assert record["comment"] == "12 pages, synthetic fixture entry"


def test_runner_parses_the_core_shape(monkeypatch):
    runner = _runner_with_json(monkeypatch, CORE_PAYLOAD)
    result = runner.query_core("Acme Holdings")

    assert result.error is None
    data = result.data
    assert data["record_count"] == 1234
    record = data["records"][0]
    assert record["record_id"] == "99999999"
    assert record["authors"] == ["Jane Acme", "P. Synthetic"]
    assert record["year"] == 2020
    assert record["download_url"] == "https://core.ac.uk/download/99999999.pdf"


def test_runner_parses_the_openaire_shape(monkeypatch):
    runner = _runner_with_json(monkeypatch, OPENAIR_E_PAYLOAD)
    result = runner.query_openaire("Acme Holdings")

    assert result.error is None
    data = result.data
    assert data["record_count"] == 7685270
    record = data["records"][0]
    assert record["record_id"] == "doi_dedup::10.9999/aletheia.synthetic.0005"
    assert record["doi"] == "10.9999/aletheia.synthetic.0005"
    assert record["publisher"] == "Synthetic Open Science Press"
    assert record["year"] == 2023


def test_runner_reports_no_match_as_an_empty_payload(monkeypatch):
    """A query with no result carries no data, so the parser emits no finding."""
    runner = _runner_with_json(monkeypatch, {"meta": {"count": 0}, "results": []})
    result = runner.query_openalex("No Such Academic Record")

    assert result.data is None
    assert result.error is None
    assert result.http_status == 200


def test_runner_reports_an_http_error_as_an_error_result(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(
        runner, "_fetch_json", lambda url, params=None, headers=None: (None, 429, "HTTP 429: Too Many Requests")
    )
    result = runner.query_semantic_scholar("Acme Holdings")

    assert result.data is None
    assert result.http_status == 429
    assert result.error == "HTTP 429: Too Many Requests"


def test_runner_never_prints_a_configured_secret(monkeypatch):
    """A configured key is sent as a header but never echoed in the payload."""
    runner = _load_runner()
    monkeypatch.setenv("OPENALEX_API_KEY", "secret-openalex-value")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "secret-s2-value")
    monkeypatch.setenv("CORE_API_KEY", "secret-core-value")
    monkeypatch.setattr(runner, "_fetch_json", lambda url, params=None, headers=None: ({}, 200, None))

    for source in ("openalex", "semantic-scholar", "core"):
        result = _runner_function(runner, source)("Acme Holdings")
        # An empty payload yields no data, so nothing that could carry the key is
        # ever serialized into the runner output.
        assert result.data is None
        assert "secret-" not in json.dumps(result.to_dict())
