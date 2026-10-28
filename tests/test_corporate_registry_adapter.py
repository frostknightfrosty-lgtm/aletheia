"""Parser + fixture tests for the corporate_registry batch adapter."""

import hashlib
import importlib.util
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

from aletheia.adapters.corporate_registry import (
    CorporateRegistryAdapter,
    CorporateRegistryFinding,
    UNSUPPORTED_SUB_SOURCES,
    _extract_details,
    _extract_record_type,
    _extract_subject,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIXTURE_PATH = "tests/fixtures/corporate_registry.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = (
    "companies-house",
    "nzbn",
    "kvk-opendata",
    "kvk-zoeken",
    "recherche-entreprises",
)

SKIP_REASONS = {
    "inpi-rne": "INPI RNE exposes no documented free search API (bulk SFTP and dataset APIs only)",
    "asic": "ASIC publishes no public JSON search API; ASIC Connect is web-only and DSP applications are closed until 2027",
    "cipc": "CIPC provides no public API; enterprise search is web-only",
}


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "corporate_registry_runner", ROOT / "docker" / "corporate_registry" / "runner.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- subject extraction --------------------------------------------------------


def test_extract_subject_companies_house():
    data = {"items": [{"company_number": "01234567", "title": "ACME HOLDINGS LIMITED"}]}
    result = _extract_subject(data, "companies-house")
    assert result == "COMPANIES_HOUSE:01234567:ACME HOLDINGS LIMITED"


def test_extract_subject_nzbn():
    data = {"items": [{"nzbn": "9429000000000", "entityName": "ACME HOLDINGS LIMITED"}]}
    result = _extract_subject(data, "nzbn")
    assert result == "NZBN:9429000000000:ACME HOLDINGS LIMITED"


def test_extract_subject_kvk_opendata():
    data = {"kvkNummer": "12345678", "naam": "Acme Holdings B.V."}
    result = _extract_subject(data, "kvk-opendata")
    assert result == "KVK:12345678:Acme Holdings B.V."


def test_extract_subject_kvk_zoeken():
    data = {"resultaten": [{"kvkNummer": "12345678", "naam": "Acme Holdings B.V."}]}
    result = _extract_subject(data, "kvk-zoeken")
    assert result == "KVK_ZOEKEN:12345678:Acme Holdings B.V."


def test_extract_subject_recherche_entreprises():
    data = {"results": [{"siren": "123456789", "nom_complet": "ACME HOLDINGS"}]}
    result = _extract_subject(data, "recherche-entreprises")
    assert result == "RNE:123456789:ACME HOLDINGS"


# -- record type extraction ----------------------------------------------------


def test_extract_record_type():
    cases = [
        ("companies-house", "company_search_result"),
        ("nzbn", "nz_business_entity"),
        ("kvk-opendata", "kvk_basisbedrijfsgegevens"),
        ("kvk-zoeken", "kvk_search_result"),
        ("recherche-entreprises", "french_company"),
        ("inpi-rne", None),
        ("asic", None),
        ("cipc", None),
    ]
    for source, expected in cases:
        data = {"dummy": True}
        result = _extract_record_type(data, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


# -- details extraction --------------------------------------------------------


def test_extract_details_companies_house():
    data = {
        "items": [
            {
                "company_number": "01234567",
                "company_status": "active",
                "company_type": "ltd",
                "date_of_creation": "1998-04-15",
                "address_snippet": "1 Example Street, London, EC1A 1AA",
            }
        ],
        "total_results": 1,
    }
    result = _extract_details(data, "companies-house")
    assert result["company_number"] == "01234567"
    assert result["company_status"] == "active"
    assert result["total_results"] == 1


def test_extract_details_nzbn():
    data = {"items": [{"nzbn": "9429000000000", "entityStatus": "Registered"}], "totalItems": 1}
    result = _extract_details(data, "nzbn")
    assert result["entity_status"] == "Registered"
    assert result["total_items"] == 1


def test_extract_details_kvk_opendata():
    data = {"kvkNummer": "12345678", "naam": "Acme Holdings B.V.", "sbiActiviteiten": [{"sbiCode": "6420"}]}
    result = _extract_details(data, "kvk-opendata")
    assert result["kvk_number"] == "12345678"
    assert result["sbi_codes"] == ["6420"]


def test_extract_details_kvk_zoeken():
    data = {"resultaten": [{"kvkNummer": "12345678"}], "totaal": 1}
    result = _extract_details(data, "kvk-zoeken")
    assert result["count"] == 1
    assert result["kvk_numbers"] == ["12345678"]


def test_extract_details_recherche_entreprises():
    data = {
        "results": [
            {
                "siren": "123456789",
                "nom_complet": "ACME HOLDINGS",
                "siege": {"siret": "12345678900012"},
            }
        ],
        "total_results": 1,
    }
    result = _extract_details(data, "recherche-entreprises")
    assert result["siren"] == "123456789"
    assert result["siret"] == "12345678900012"


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = CorporateRegistryFinding(
        subject="COMPANIES_HOUSE:01234567:ACME HOLDINGS LIMITED",
        source="companies-house",
        record_type="company_search_result",
        entity_name="Acme Holdings B.V.",
        identifier="COMPANIES_HOUSE:01234567:ACME HOLDINGS LIMITED",
        location="London",
        date="2026-10-14",
        details={"company_number": "01234567"},
        raw_evidence={"items": [{"company_number": "01234567"}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:companies-house",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from companies-house"],
        ),
    )
    assert finding.entity_type.value == "company_registry_record"
    assert finding.attributes["source"] == "companies-house"
    assert finding.subject == "COMPANIES_HOUSE:01234567:ACME HOLDINGS LIMITED"


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 8
    assert set(sources) == set(SUPPORTED_SOURCES) | set(SKIP_REASONS)
    assert set(UNSUPPORTED_SUB_SOURCES) == set(SKIP_REASONS)

    by_source = {s["source"]: s for s in fixture["sources"]}
    for source in SUPPORTED_SOURCES:
        assert by_source[source]["skipped"] is False, source
        assert by_source[source]["data"], source
    for source, reason in SKIP_REASONS.items():
        assert by_source[source]["skipped"] is True, source
        assert by_source[source]["skip_reason"] == reason, source
        assert by_source[source]["data"] is None, source

    assert UNSUPPORTED_SUB_SOURCES["inpi-rne"] == SKIP_REASONS["inpi-rne"]
    assert UNSUPPORTED_SUB_SOURCES["asic"] == SKIP_REASONS["asic"]
    assert UNSUPPORTED_SUB_SOURCES["cipc"] == SKIP_REASONS["cipc"]


# -- run result parsing --------------------------------------------------------


def _request(value: str = "Acme Holdings B.V.") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.COMPANY_NAME, value=value), legal_only=True
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
            "input_type": "company_name",
            "input_value": "Acme Holdings B.V.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
        }
    )


@parser_test("corporate_registry")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = CorporateRegistryAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 8

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES) | set(SKIP_REASONS)

    companies_house = by_source["companies-house"]
    assert companies_house.value == "COMPANIES_HOUSE:01234567:ACME HOLDINGS LIMITED"
    assert companies_house.subject == "COMPANIES_HOUSE:01234567:ACME HOLDINGS LIMITED"
    assert companies_house.record_type == "company_search_result"
    assert companies_house.entity_name == "Acme Holdings B.V."
    assert companies_house.attributes["details"]["company_number"] == "01234567"
    assert companies_house.attributes["details"]["company_status"] == "active"
    assert companies_house.attributes["date"] == fixture["sources"][0]["timestamp"][:10]

    nzbn = by_source["nzbn"]
    assert nzbn.value == "NZBN:9429000000000:ACME HOLDINGS LIMITED"
    assert nzbn.record_type == "nz_business_entity"
    assert nzbn.attributes["details"]["entity_status"] == "Registered"

    kvk_opendata = by_source["kvk-opendata"]
    assert kvk_opendata.value == "KVK:12345678:Acme Holdings B.V."
    assert kvk_opendata.record_type == "kvk_basisbedrijfsgegevens"
    assert kvk_opendata.attributes["details"]["sbi_codes"] == ["6420"]

    kvk_zoeken = by_source["kvk-zoeken"]
    assert kvk_zoeken.value == "KVK_ZOEKEN:12345678:Acme Holdings B.V."
    assert kvk_zoeken.record_type == "kvk_search_result"
    assert kvk_zoeken.attributes["details"]["count"] == 1

    recherche = by_source["recherche-entreprises"]
    assert recherche.value == "RNE:123456789:ACME HOLDINGS"
    assert recherche.record_type == "french_company"
    assert recherche.attributes["details"]["siret"] == "12345678900012"

    for source, reason in SKIP_REASONS.items():
        skipped = by_source[source]
        assert skipped.value == f"{source}:skipped"
        assert skipped.record_type is None
        assert skipped.attributes["details"] == {"skipped": True, "reason": reason}
        assert skipped.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
        assert f"Skipped: {reason}" in skipped.provenance.notes

    for finding in result.findings:
        assert isinstance(finding, CorporateRegistryFinding)
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.COMPANY_REGISTRY_RECORD)
        assert finding.provenance.tool == "corporate_registry"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80
        raw = finding.attributes["raw_evidence"]
        assert raw
        assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
            json.dumps(raw, sort_keys=True).encode()
        ).hexdigest()


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    payload = _payload(
        [
            _source(
                "asic",
                skipped=True,
                skip_reason=SKIP_REASONS["asic"],
                http_status=0,
                data=None,
            )
        ]
    )

    adapter = CorporateRegistryAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "asic"
    assert finding.value == "asic:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": SKIP_REASONS["asic"]}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": SKIP_REASONS["asic"]}
    assert f"Skipped: {SKIP_REASONS['asic']}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not a record."""
    payload = _payload(
        [_source("companies-house", http_status=401, error="HTTP 401: Unauthorized")]
    )

    adapter = CorporateRegistryAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "companies-house"
    assert finding.value == "companies-house:error"
    assert finding.attributes["details"] == {
        "error": "HTTP 401: Unauthorized",
        "http_status": 401,
    }
    assert "Error: HTTP 401: Unauthorized" in finding.provenance.notes

    # A sub-source error must not be reported as a successful record.
    assert finding.record_type is None
    assert finding.attributes.get("raw_evidence") == {
        "error": "HTTP 401: Unauthorized",
        "http_status": 401,
    }
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
        json.dumps(finding.attributes["raw_evidence"], sort_keys=True).encode()
    ).hexdigest()


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = CorporateRegistryAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = CorporateRegistryAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = CorporateRegistryAdapter()
    assert adapter.supports(SeedType.NAME)
    assert adapter.supports(SeedType.COMPANY_NAME)
    assert not adapter.supports(SeedType.PERSON_NAME)


def test_adapter_input_types():
    adapter = CorporateRegistryAdapter()
    type_map = {
        SeedType.NAME: "name",
        SeedType.COMPANY_NAME: "company_name",
    }
    for seed_type, expected in type_map.items():
        seed_obj = type("Seed", (), {"type": seed_type, "value": "test_val"})()
        req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
        cmd = adapter.build_command(req, None)
        assert cmd[0] == expected, f"{seed_type}: expected {expected}, got {cmd[0]}"
    assert adapter.descriptor.input_types == [SeedType.NAME, SeedType.COMPANY_NAME]


def test_adapter_build_command_name():
    adapter = CorporateRegistryAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    cmd = adapter.build_command(req, None)
    assert cmd == ["name", "test_val"]


def test_adapter_build_command_company_name():
    adapter = CorporateRegistryAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.COMPANY_NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    cmd = adapter.build_command(req, None)
    assert cmd == ["company_name", "test_val"]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "corporate_registry" in registry

    descriptor = registry["corporate_registry"].descriptor
    assert descriptor.name == "corporate_registry"
    assert descriptor.input_types == [SeedType.NAME, SeedType.COMPANY_NAME]
    assert descriptor.output_types == [EntityType.COMPANY_REGISTRY_RECORD]
    assert descriptor.docker_image == "aletheia/corp-registry:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == [
        "COMPANIES_HOUSE_API_KEY",
        "NZBN_API_SUBSCRIPTION_KEY",
        "KVK_API_KEY",
    ]
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)


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
        sys.argv = ["runner.py", "invalid_type", "Acme Holdings B.V."]
        assert runner.main() == 2
    finally:
        sys.argv = old_argv
        sys.stderr = old_stderr


def test_runner_unsupported_sub_sources_are_documented_skips():
    runner = _load_runner()
    cases = {
        "inpi-rne": (runner.query_inpi_rne, SKIP_REASONS["inpi-rne"]),
        "asic": (runner.query_asic, SKIP_REASONS["asic"]),
        "cipc": (runner.query_cipc, SKIP_REASONS["cipc"]),
    }
    for source, (query, reason) in cases.items():
        result = query("Acme Holdings B.V.")
        assert result.name == source
        assert result.skipped is True
        assert result.skip_reason == reason
        assert result.data is None
        assert result.to_dict()["skipped"] is True


def test_runner_defines_no_endpoint_for_unsupported_sources():
    runner_source = (ROOT / "docker" / "corporate_registry" / "runner.py").read_text(encoding="utf-8")
    unsupported_section = runner_source.split("def query_inpi_rne", 1)[1].split("def main", 1)[0]
    assert "https://" not in unsupported_section
    assert "http://" not in unsupported_section


def test_runner_keyed_sources_skip_without_keys(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    monkeypatch.delenv("NZBN_API_SUBSCRIPTION_KEY", raising=False)

    companies_house = runner.query_companies_house("Acme Holdings")
    assert companies_house.skipped is True
    assert companies_house.skip_reason == "COMPANIES_HOUSE_API_KEY not set"

    nzbn = runner.query_nzbn("Acme Holdings")
    assert nzbn.skipped is True
    assert nzbn.skip_reason == "NZBN_API_SUBSCRIPTION_KEY not set"


def test_runner_kvk_zoeken_is_paid_and_skipped_without_key(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv("KVK_API_KEY", raising=False)

    result = runner.query_kvk_zoeken("Acme Holdings")
    assert result.skipped is True
    assert result.data is None
    assert "paid subscription" in result.skip_reason
    assert "private use" in result.skip_reason
