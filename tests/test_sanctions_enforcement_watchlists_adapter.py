"""Parser + fixture tests for the sanctions_enforcement_watchlists batch adapter."""

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

from aletheia.adapters.sanctions_enforcement_watchlists import (
    IMPLEMENTED_ELSEWHERE,
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    SanctionsEnforcementWatchlistsAdapter,
    SanctionsEnforcementWatchlistsFinding,
    _extract_details,
    _extract_record_type,
    _extract_subject,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIXTURE_PATH = "tests/fixtures/sanctions_enforcement_watchlists.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = (
    "uk-sanctions-list",
    "swiss-seco",
    "eu-consolidated-sanctions",
)

# No sub-source of this adapter is unsupported: all three publish a documented
# bulk XML artefact that was verified against the provider's own publication
# page. A future unsupported sub-source would appear here with its exact reason
# and would be reported as a skip instead of a queried source.
SKIP_REASONS: dict[str, str] = {}

# The single published bulk artefact each implemented sub-source downloads. The
# runner resolves every URL from a module constant, so the fixture and the tests
# can check the exact artefact instead of trusting a literal in a function body.
URL_CONSTANTS = {
    "uk-sanctions-list": "UK_SANCTIONS_LIST_URL",
    "swiss-seco": "SECO_SANCTIONS_LIST_URL",
    "eu-consolidated-sanctions": "EU_SANCTIONS_LIST_URL",
}

PAGE_CONSTANTS = {
    "uk-sanctions-list": "UK_SANCTIONS_LIST_PAGE",
    "swiss-seco": "SECO_SANCTIONS_LIST_PAGE",
    "eu-consolidated-sanctions": "EU_SANCTIONS_LIST_PAGE",
}


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "sanctions_enforcement_watchlists_runner",
        ROOT / "docker" / "sanctions_enforcement_watchlists" / "runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_function(module, source: str):
    return getattr(module, "query_" + source.replace("-", "_"))


# -- subject extraction --------------------------------------------------------


def test_extract_subject_uk_sanctions_list():
    data = {"matches": [{"unique_id": "RUS0999", "primary_name": "ACME HOLDINGS LIMITED"}]}
    assert _extract_subject(data, "uk-sanctions-list") == "UK_SANCTIONS:RUS0999:ACME HOLDINGS LIMITED"


def test_extract_subject_swiss_seco():
    data = {"matches": [{"ssid": "900001", "primary_name": "ACME HOLDINGS AG"}]}
    assert _extract_subject(data, "swiss-seco") == "SECO:900001:ACME HOLDINGS AG"


def test_extract_subject_eu_consolidated_sanctions():
    data = {"matches": [{"eu_reference_number": "EU.9000.13", "primary_name": "ACME HOLDINGS OOO"}]}
    assert _extract_subject(data, "eu-consolidated-sanctions") == "EU_SANCTIONS:EU.9000.13:ACME HOLDINGS OOO"


def test_extract_subject_without_a_match_falls_back_to_source():
    """A payload with no match never claims a designation subject."""
    for source in SUPPORTED_SOURCES:
        assert _extract_subject({"matches": [], "match_count": 0}, source) == source


# -- record type extraction ----------------------------------------------------


def test_extract_record_type():
    cases = [
        ("uk-sanctions-list", "uk_sanctions_designation"),
        ("swiss-seco", "swiss_seco_sanctions_target"),
        ("eu-consolidated-sanctions", "eu_financial_sanctions_designation"),
        ("finra-brokercheck", None),
        ("unknown-source", None),
    ]
    for source, expected in cases:
        result = _extract_record_type({"dummy": True}, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


# -- details extraction --------------------------------------------------------


def test_extract_details_uk_sanctions_list():
    data = {
        "list_url": "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml",
        "date_generated": "12/10/2026",
        "match_count": 1,
        "truncated": False,
        "matches": [
            {
                "unique_id": "RUS0999",
                "ofsi_group_id": "99001",
                "subject_kind": "Entity",
                "regime_name": "The Russia (Sanctions) (EU Exit) Regulations 2019",
                "sanctions_imposed": "Asset freeze",
                "date_designated": "15/03/2022",
                "matched_names": ["ACME HOLDINGS LIMITED"],
            }
        ],
    }
    result = _extract_details(data, "uk-sanctions-list")
    assert result["unique_id"] == "RUS0999"
    assert result["regime_name"] == "The Russia (Sanctions) (EU Exit) Regulations 2019"
    assert result["match_count"] == 1
    assert result["truncated"] is False


def test_extract_details_swiss_seco():
    data = {
        "list_url": "https://www.sesam.search.admin.ch/sesam-search-web/pages/downloadXmlGesamtliste.xhtml",
        "list_date": "2026-10-05",
        "list_type": "whole-list",
        "match_count": 1,
        "matches": [
            {
                "ssid": "900001",
                "subject_type": "entity",
                "program_key": "Belarus",
                "program_origin": "EU",
                "sanctions_set_ids": ["4387"],
                "matched_names": ["ACME HOLDINGS AG"],
            }
        ],
    }
    result = _extract_details(data, "swiss-seco")
    assert result["ssid"] == "900001"
    assert result["program_key"] == "Belarus"
    assert result["sanctions_set_ids"] == ["4387"]
    assert result["list_date"] == "2026-10-05"


def test_extract_details_eu_consolidated_sanctions():
    data = {
        "list_url": "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content",
        "generation_date": "2026-10-12T12:27:34.779+02:00",
        "global_file_id": "185689",
        "match_count": 1,
        "matches": [
            {
                "logical_id": "900013",
                "eu_reference_number": "EU.9000.13",
                "subject_type": "enterprise",
                "programme": "RUS",
                "regulation_number_title": "269/2014 (OJ L78)",
                "matched_names": ["ACME HOLDINGS OOO"],
            }
        ],
    }
    result = _extract_details(data, "eu-consolidated-sanctions")
    assert result["logical_id"] == "900013"
    assert result["eu_reference_number"] == "EU.9000.13"
    assert result["programme"] == "RUS"
    assert result["global_file_id"] == "185689"


def test_extract_details_without_a_match_is_none():
    assert _extract_details({"matches": []}, "uk-sanctions-list") is None


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = SanctionsEnforcementWatchlistsFinding(
        subject="UK_SANCTIONS:RUS0999:ACME HOLDINGS LIMITED",
        source="uk-sanctions-list",
        record_type="uk_sanctions_designation",
        entity_name="Acme Holdings",
        identifier="UK_SANCTIONS:RUS0999:ACME HOLDINGS LIMITED",
        jurisdiction="GB",
        date="2026-10-15",
        details={"unique_id": "RUS0999"},
        raw_evidence={"matches": [{"unique_id": "RUS0999"}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:uk-sanctions-list",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from uk-sanctions-list"],
        ),
    )
    assert finding.entity_type == EntityType.SANCTION
    assert finding.entity_type.value == "sanction"
    assert finding.attributes["source"] == "uk-sanctions-list"
    assert finding.attributes["jurisdiction"] == "GB"
    assert finding.subject == "UK_SANCTIONS:RUS0999:ACME HOLDINGS LIMITED"


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    runner = _load_runner()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 3
    assert set(sources) == set(SUPPORTED_SOURCES)
    assert set(UNSUPPORTED_SUB_SOURCES) == set(SKIP_REASONS)
    assert UNSUPPORTED_SUB_SOURCES == {}
    assert tuple(runner.SUPPORTED_SUB_SOURCES) == tuple(SUPPORTED_SOURCES)

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
        assert entry["data"]["list_url"] == getattr(runner, URL_CONSTANTS[source]), source
        assert entry["data"]["list_publication_page"] == getattr(runner, PAGE_CONSTANTS[source]), source


def test_fixture_uses_only_synthetic_values():
    """The fixture is synthetic and must not read as captured live output."""
    fixture = load_fixture()
    for entry in fixture["sources"]:
        for match in entry["data"]["matches"]:
            assert "ACME HOLDINGS" in match["primary_name"], entry["source"]


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


@parser_test("sanctions_enforcement_watchlists")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = SanctionsEnforcementWatchlistsAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 3

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES)

    uk = by_source["uk-sanctions-list"]
    assert uk.value == "UK_SANCTIONS:RUS0999:ACME HOLDINGS LIMITED"
    assert uk.subject == "UK_SANCTIONS:RUS0999:ACME HOLDINGS LIMITED"
    assert uk.record_type == "uk_sanctions_designation"
    assert uk.entity_name == "Acme Holdings"
    assert uk.attributes["jurisdiction"] == "GB"
    assert uk.attributes["details"]["unique_id"] == "RUS0999"
    assert uk.attributes["details"]["regime_name"] == "The Russia (Sanctions) (EU Exit) Regulations 2019"
    assert uk.attributes["details"]["sanctions_imposed"] == "Asset freeze"
    assert uk.attributes["date"] == fixture["sources"][0]["timestamp"][:10]

    seco = by_source["swiss-seco"]
    assert seco.value == "SECO:900001:ACME HOLDINGS AG"
    assert seco.record_type == "swiss_seco_sanctions_target"
    assert seco.attributes["jurisdiction"] == "CH"
    assert seco.attributes["details"]["program_key"] == "Belarus"
    assert seco.attributes["details"]["sanctions_set_ids"] == ["4387"]

    eu = by_source["eu-consolidated-sanctions"]
    assert eu.value == "EU_SANCTIONS:EU.9000.13:ACME HOLDINGS OOO"
    assert eu.record_type == "eu_financial_sanctions_designation"
    assert eu.attributes["jurisdiction"] == "EU"
    assert eu.attributes["details"]["programme"] == "RUS"
    assert eu.attributes["details"]["regulation_number_title"] == "269/2014 (OJ L78)"

    for finding in result.findings:
        assert isinstance(finding, SanctionsEnforcementWatchlistsFinding)
        assert finding.entity_type == EntityType.SANCTION
        assert finding.provenance.tool == "sanctions_enforcement_watchlists"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80

    _assert_provenance_hash_invariant(result.findings)

    # A mixed runner payload must yield a real finding, a skip finding and an
    # error finding, each with the same provenance hash invariant.
    mixed = _payload(
        [
            _source("uk-sanctions-list", data=fixture["sources"][0]["data"],
                    raw_hash=fixture["sources"][0]["raw_hash"]),
            _source(
                "swiss-seco",
                skipped=True,
                skip_reason="SECO XML consolidated list was unavailable for this run",
                http_status=0,
            ),
            _source(
                "eu-consolidated-sanctions",
                http_status=503,
                error="HTTP 503: Service Unavailable",
            ),
        ]
    )
    mixed_result = adapter.parse(_request(), Path("."), mixed, "", 0)

    assert mixed_result.status == "succeeded"
    assert len(mixed_result.findings) == 3
    mixed_by_source = {f.attributes["source"]: f for f in mixed_result.findings}

    ok_finding = mixed_by_source["uk-sanctions-list"]
    assert ok_finding.value == "UK_SANCTIONS:RUS0999:ACME HOLDINGS LIMITED"
    assert ok_finding.record_type == "uk_sanctions_designation"

    skipped_finding = mixed_by_source["swiss-seco"]
    assert skipped_finding.value == "swiss-seco:skipped"
    assert skipped_finding.record_type is None
    assert skipped_finding.attributes["details"] == {
        "skipped": True,
        "reason": "SECO XML consolidated list was unavailable for this run",
    }
    assert "Skipped: SECO XML consolidated list was unavailable for this run" in skipped_finding.provenance.notes

    error_finding = mixed_by_source["eu-consolidated-sanctions"]
    assert error_finding.value == "eu-consolidated-sanctions:error"
    assert error_finding.record_type is None
    assert error_finding.attributes["details"] == {
        "error": "HTTP 503: Service Unavailable",
        "http_status": 503,
    }
    assert "Error: HTTP 503: Service Unavailable" in error_finding.provenance.notes

    for finding in mixed_result.findings:
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.SANCTION)
    _assert_provenance_hash_invariant(mixed_result.findings)


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    reason = "SECO XML consolidated list was unavailable for this run"
    payload = _payload([_source("swiss-seco", skipped=True, skip_reason=reason, http_status=0)])

    adapter = SanctionsEnforcementWatchlistsAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "swiss-seco"
    assert finding.value == "swiss-seco:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": reason}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
    assert f"Skipped: {reason}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not a designation."""
    payload = _payload(
        [_source("eu-consolidated-sanctions", http_status=403, error="HTTP 403: Forbidden")]
    )

    adapter = SanctionsEnforcementWatchlistsAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "eu-consolidated-sanctions"
    assert finding.value == "eu-consolidated-sanctions:error"
    assert finding.attributes["details"] == {
        "error": "HTTP 403: Forbidden",
        "http_status": 403,
    }
    assert "Error: HTTP 403: Forbidden" in finding.provenance.notes

    # A sub-source error must not be reported as a successful designation.
    assert finding.record_type is None
    assert finding.attributes.get("raw_evidence") == {
        "error": "HTTP 403: Forbidden",
        "http_status": 403,
    }
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
        json.dumps(finding.attributes["raw_evidence"], sort_keys=True).encode()
    ).hexdigest()


def test_parse_no_match_produces_no_finding():
    """A source with no match must not be reported as a sanction."""
    payload = _payload([_source("uk-sanctions-list", data=None, raw_hash=None)])

    adapter = SanctionsEnforcementWatchlistsAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = SanctionsEnforcementWatchlistsAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = SanctionsEnforcementWatchlistsAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = SanctionsEnforcementWatchlistsAdapter()
    assert adapter.supports(SeedType.NAME)
    assert adapter.supports(SeedType.COMPANY_NAME)
    assert adapter.supports(SeedType.PERSON_NAME)
    assert not adapter.supports(SeedType.EMAIL)


def test_adapter_input_types():
    adapter = SanctionsEnforcementWatchlistsAdapter()
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
    adapter = SanctionsEnforcementWatchlistsAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["name", "test_val"]


def test_adapter_build_command_company_name():
    adapter = SanctionsEnforcementWatchlistsAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.COMPANY_NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["company_name", "test_val"]


def test_adapter_build_command_person_name():
    adapter = SanctionsEnforcementWatchlistsAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.PERSON_NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["person_name", "test_val"]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "sanctions_enforcement_watchlists" in registry

    descriptor = registry["sanctions_enforcement_watchlists"].descriptor
    assert descriptor.name == "sanctions_enforcement_watchlists"
    assert descriptor.input_types == [SeedType.NAME, SeedType.COMPANY_NAME, SeedType.PERSON_NAME]
    assert descriptor.output_types == [EntityType.SANCTION]
    assert descriptor.docker_image == "aletheia/sanctions-watchlists:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == []
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)
    assert descriptor.upstream.endswith("docker/sanctions_enforcement_watchlists")


def test_adapter_documents_the_government_records_us_overlap():
    """The three overlapping batch-plan sub-sources stay in government_records_us."""
    assert IMPLEMENTED_ELSEWHERE == {
        "finra-brokercheck": "government_records_us",
        "fed-enforcement": "government_records_us",
        "occ-enforcement": "government_records_us",
    }
    assert not set(IMPLEMENTED_ELSEWHERE) & set(SUPPORTED_SUB_SOURCES)

    runner_source = (ROOT / "docker" / "government_records_us" / "runner.py").read_text(encoding="utf-8")
    for function_name in ("query_finra", "query_fed_enforcement", "query_occ_enforcement"):
        assert f"def {function_name}(" in runner_source

    adapter_source = (
        ROOT / "app" / "aletheia" / "adapters" / "sanctions_enforcement_watchlists.py"
    ).read_text(encoding="utf-8")
    for sub_source in IMPLEMENTED_ELSEWHERE:
        assert sub_source not in SUPPORTED_SUB_SOURCES
        assert f"def query_{sub_source.replace('-', '_')}(" not in (
            ROOT / "docker" / "sanctions_enforcement_watchlists" / "runner.py"
        ).read_text(encoding="utf-8")
    assert "government_records_us" in adapter_source


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
    """Unsupported sub-sources are auditable skips with no URL, never a guessed call."""
    runner = _load_runner()
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES
    for source, reason in UNSUPPORTED_SUB_SOURCES.items():
        assert isinstance(reason, str) and reason.strip()
        function_source = inspect.getsource(_runner_function(runner, source))
        assert "http://" not in function_source
        assert "https://" not in function_source


def test_runner_supported_sources_cite_a_published_artefact():
    """Every implemented sub-source queries one documented bulk artefact URL."""
    runner = _load_runner()
    for source in SUPPORTED_SUB_SOURCES:
        url = getattr(runner, URL_CONSTANTS[source])
        page = getattr(runner, PAGE_CONSTANTS[source])
        assert url.startswith("https://"), source
        assert page.startswith("https://"), source
        # The artefact is a published XML bulk file, never a constructed JSON API.
        assert url.endswith(".xml") or "downloadXmlGesamtliste" in url or "/content" in url, source
        function_source = inspect.getsource(_runner_function(runner, source))
        assert URL_CONSTANTS[source] in function_source, source
        assert "json" not in function_source.casefold(), source


# -- runner parsing against the published document shapes ----------------------
#
# The three artefacts below are minimal synthetic documents that follow the
# structure of the real published files (verified while writing the runner):
# the UK Sanctions List XML has one Designation per designation with ordered
# Name parts, the SECO whole list has sanctions-program and target elements with
# a final modification per target, and the EU FSF export is namespaced with
# sanctionEntity elements. No network is used: the fetch helper is replaced.

UK_LIST_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<Designations>
  <DateGenerated>12/10/2026</DateGenerated>
  <Designation>
    <LastUpdated>12/10/2026</LastUpdated>
    <DateDesignated>15/03/2022</DateDesignated>
    <UniqueID>RUS0999</UniqueID>
    <OFSIGroupID>99001</OFSIGroupID>
    <UNReferenceNumber></UNReferenceNumber>
    <Names>
      <Name><Name1>ACME</Name1><Name2>HOLDINGS LIMITED</Name2><NameType>Primary Name</NameType></Name>
      <Name><Name6>ACME HOLDING LTD</Name6><NameType>Alias</NameType></Name>
    </Names>
    <RegimeName>The Russia (Sanctions) (EU Exit) Regulations 2019</RegimeName>
    <IndividualEntityShip>Entity</IndividualEntityShip>
    <DesignationSource>UK</DesignationSource>
    <SanctionsImposed>Asset freeze</SanctionsImposed>
  </Designation>
  <Designation>
    <UniqueID>UNK0001</UniqueID>
    <Names><Name><Name6>UNRELATED PERSON</Name6><NameType>Primary Name</NameType></Name></Names>
  </Designation>
</Designations>
"""

SECO_LIST_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<swiss-sanctions-list list-type="whole-list" date="2026-10-05">
  <sanctions-program ssid="20" version-date="2026-05-21" predecessor-version-date="2025-12-12">
    <program-key lang="eng">Belarus</program-key>
    <program-key lang="ger">Belarus</program-key>
    <sanctions-set ssid="4387" lang="eng">article 12 (Financial sanctions), annexe 13</sanctions-set>
    <origin>EU</origin>
  </sanctions-program>
  <target ssid="900001">
    <sanctions-set-id>4387</sanctions-set-id>
    <entity>
      <identity ssid="1" main="true">
        <name ssid="2" name-type="primary-name" lang="eng">
          <name-part order="1" name-part-type="whole-name"><value>ACME HOLDINGS AG</value></name-part>
        </name>
        <name ssid="3" name-type="alias" lang="eng">
          <name-part order="1" name-part-type="whole-name"><value>ACME HOLDINGS ANSTALT</value></name-part>
        </name>
      </identity>
    </entity>
    <modification modification-type="listed" enactment-date="2022-03-16"/>
  </target>
  <target ssid="900002">
    <sanctions-set-id>4387</sanctions-set-id>
    <entity>
      <identity ssid="4" main="true">
        <name ssid="5" name-type="primary-name" lang="eng">
          <name-part order="1" name-part-type="whole-name"><value>ACME HOLDINGS DELISTED AG</value></name-part>
        </name>
      </identity>
    </entity>
    <modification modification-type="listed" enactment-date="2020-01-01"/>
    <modification modification-type="de-listed" enactment-date="2024-01-01"/>
  </target>
</swiss-sanctions-list>
"""

EU_LIST_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<export xmlns="http://eu.europa.ec/fpi/fsd/export" generationDate="2026-10-12T12:27:34.779+02:00" globalFileId="185689">
  <sanctionEntity designationDetails="" unitedNationId="" euReferenceNumber="EU.9000.13" logicalId="900013">
    <remark>synthetic fixture remark</remark>
    <regulation regulationType="regulation" organisationType="council" publicationDate="2014-03-17" numberTitle="269/2014 (OJ L78)" programme="RUS" logicalId="348">
      <publicationUrl>http://example.invalid/</publicationUrl>
    </regulation>
    <subjectType code="enterprise" classificationCode="E"/>
    <nameAlias wholeName="ACME HOLDINGS OOO" strong="true" logicalId="17"/>
  </sanctionEntity>
</export>
"""


def _runner_with_body(monkeypatch, body: bytes):
    runner = _load_runner()
    monkeypatch.setattr(
        runner, "_fetch_bytes", lambda url, timeout=120, max_bytes=0: (body, 200, None)
    )
    return runner


def test_runner_parses_the_published_uk_sanctions_list_shape(monkeypatch):
    runner = _runner_with_body(monkeypatch, UK_LIST_XML)
    result = runner.query_uk_sanctions_list("Acme Holdings")

    assert result.error is None
    assert result.http_status == 200
    data = result.data
    assert data["date_generated"] == "12/10/2026"
    assert data["match_count"] == 1
    match = data["matches"][0]
    assert match["unique_id"] == "RUS0999"
    assert match["primary_name"] == "ACME HOLDINGS LIMITED"
    assert match["matched_names"] == ["ACME HOLDINGS LIMITED"]
    assert match["regime_name"] == "The Russia (Sanctions) (EU Exit) Regulations 2019"


def test_runner_parses_the_published_seco_shape_and_skips_de_listed_targets(monkeypatch):
    runner = _runner_with_body(monkeypatch, SECO_LIST_XML)
    result = runner.query_swiss_seco("Acme Holdings")

    assert result.error is None
    data = result.data
    assert data["list_type"] == "whole-list"
    assert data["list_date"] == "2026-10-05"
    # The de-listed target of the same list must not be reported as current.
    assert data["match_count"] == 1
    match = data["matches"][0]
    assert match["ssid"] == "900001"
    assert match["primary_name"] == "ACME HOLDINGS AG"
    assert match["subject_type"] == "entity"
    assert match["sanctions_set_ids"] == ["4387"]
    assert match["program_key"] == "Belarus"
    assert match["program_origin"] == "EU"


def test_runner_parses_the_published_eu_shape(monkeypatch):
    runner = _runner_with_body(monkeypatch, EU_LIST_XML)
    result = runner.query_eu_consolidated_sanctions("Acme Holdings")

    assert result.error is None
    data = result.data
    assert data["global_file_id"] == "185689"
    assert data["generation_date"].startswith("2026-10-12T12:27:34")
    match = data["matches"][0]
    assert match["eu_reference_number"] == "EU.9000.13"
    assert match["logical_id"] == "900013"
    assert match["subject_type"] == "enterprise"
    assert match["programme"] == "RUS"


def test_runner_reports_no_match_as_an_empty_payload(monkeypatch):
    """A query with no match carries no data, so the parser emits no finding."""
    runner = _runner_with_body(monkeypatch, UK_LIST_XML)
    result = runner.query_uk_sanctions_list("No Such Listed Person")

    assert result.data is None
    assert result.error is None
    assert result.http_status == 200
