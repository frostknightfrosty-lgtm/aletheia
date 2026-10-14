"""Parser + fixture tests for the government_records_us batch adapter."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.core.models import (
    AdapterRunRequest,
    EntityType,
    Finding,
    Provenance,
    Seed,
    SeedType,
)

from aletheia.adapters.government_records_us import (
    GovernmentRecordsUSAdapter,
    GovernmentRecordsUSFinding,
    _extract_record_type,
    _extract_subject,
    _extract_details,
)


# ── fixture ────────────────────────────────────────────────────────────────────

EXPECTED_FIXTURE_PATH = "tests/fixtures/government_records_us.json"


def load_fixture():
    with open(EXPECTED_FIXTURE_PATH, "r") as f:
        return json.load(f)


# ── subject extraction ─────────────────────────────────────────────────────────


def test_extract_subject_finra():
    data = {
        "data": [
            {
                "crd": 1234567,
                "firstName": "John",
                "lastName": "Smith",
                "iaScope": "I",
            }
        ]
    }
    result = _extract_subject(data, "finra-brokercheck")
    assert result == "FINRA:1234567:John Smith"


def test_extract_subject_fdic():
    data = {"data": [{"CERT": "37212", "NAME": "First National Bank"}]}
    result = _extract_subject(data, "fdic-bankfind")
    assert result == "FDIC:37212:First National Bank"


def test_extract_subject_fed_enforcement():
    data = {
        "results": [
            {
                "individual": "John Smith",
                "bankingOrganization": "First National Bank",
            }
        ]
    }
    result = _extract_subject(data, "fed-enforcement")
    assert result.startswith("FED:")


def test_extract_subject_occ():
    data = {"enforcementActions": [{"bankName": "First National Bank"}]}
    result = _extract_subject(data, "occ-enforcement")
    assert result.startswith("OCC:")


def test_extract_subject_usaspending():
    data = {"results": [{"recipient_name": "ABC Corp", "recipient_id": "ID123"}]}
    result = _extract_subject(data, "usaspending")
    assert result.startswith("USASPENDING:")


def test_extract_subject_sam():
    data = {"entityData": [{"entityId": "E456", "entityName": "Acme Inc"}]}
    result = _extract_subject(data, "sam-gov")
    assert result.startswith("SAM:")


def test_extract_subject_lda():
    data = {"results": [{"clientName": "John Doe", "filingUuid": "F789"}]}
    result = _extract_subject(data, "lda")
    assert result.startswith("LDA:")


def test_extract_subject_foia():
    data = {"data": [{"id": "FOIA-001", "name": "Treasury Dept"}]}
    result = _extract_subject(data, "foia-gov")
    assert result.startswith("FOIA:")


def test_extract_subject_nhtsa():
    data = {"Results": [{"VIN": "1HGCM82633A123456"}]}
    result = _extract_subject(data, "nhtsa-vpic")
    assert result.startswith("NHTSA:")


def test_extract_subject_bop():
    data = {"InmateLocator": [{"inmateNum": "12345-060", "nameLast": "SMITH"}]}
    result = _extract_subject(data, "bop-inmate-locator")
    assert result.startswith("BOP:")


def test_extract_subject_nyc():
    data = [
        {"unique_key": "100", "complaint_type": "Noise Complaint"}
    ]
    result = _extract_subject(data, "nyc-open-data")
    assert result.startswith("NYC:")


# ── record type extraction ─────────────────────────────────────────────────────


def test_extract_record_type():
    cases = [
        ("finra-brokercheck", "broker_check"),
        ("fdic-bankfind", "bank_institution"),
        ("fed-enforcement", "enforcement_action"),
        ("occ-enforcement", "occ_enforcement"),
        ("usaspending", "federal_award"),
        ("sam-gov", "entity_registration"),
        ("lda", "lobbying_filing"),
        ("foia-gov", "foia_agency"),
        ("nhtsa-vpic", "vehicle_specs"),
        ("bop-inmate-locator", "inmate_record"),
        ("nyc-open-data", "311_service_request"),
    ]
    for source, expected in cases:
        data = {"dummy": True}
        result = _extract_record_type(data, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


# ── details extraction ─────────────────────────────────────────────────────────


def test_extract_details_finra():
    data = {
        "data": [
            {
                "crd": 1234567,
                "bcScope": "A",
                "iaScope": "I",
                "hasBcDisclosure": False,
                "hasIaDisclosure": True,
                "isPermanentlyBarred": False,
                "approvedFinnaRegistrationCount": 3,
            }
        ]
    }
    result = _extract_details(data, "finra-brokercheck")
    assert result["crd"] == 1234567
    assert result["barred"] is False
    assert result["has_bc_disclosure"] is False


def test_extract_details_fdic():
    data = {"data": [{"CERT": "37212", "NAME": "First National Bank", "CITY": "New York"}]}
    result = _extract_details(data, "fdic-bankfind")
    assert result["CERT"] == "37212"


def test_extract_details_bop():
    data = {"InmateLocator": [{"inmateNum": "12345-060", "nameLast": "SMITH", "age": "45"}]}
    result = _extract_details(data, "bop-inmate-locator")
    assert result["count"] >= 1


def test_extract_details_nyc():
    data = [
        {"complaint_type": "Noise Complaint"},
        {"complaint_type": "Traffic Violation"},
    ]
    result = _extract_details(data, "nyc-open-data")
    assert isinstance(result, dict)


# ── finding schema ─────────────────────────────────────────────────────────────


def test_finding_can_construct():
    from aletheia.core.models import Provenance

    finding = GovernmentRecordsUSFinding(
        subject="FINRA:1234567:John Smith",
        source="finra-brokercheck",
        record_type="broker_check",
        entity_name="John Smith",
        identifier="FINRA:1234567:John Smith",
        location="New York",
        date="2024-01-15",
        details={"crd": 1234567},
        raw_evidence={"data": "test"},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:finra-brokercheck",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from finra-brokercheck"],
        ),
    )
    assert finding.entity_type.value == "government_record"
    assert finding.attributes["source"] == "finra-brokercheck"


def test_finding_from_fixture():
    fixture = load_fixture()
    sources = fixture["sources"]

    # FINRA sub-source
    finra_src = [s for s in sources if s["source"] == "finra-brokercheck"][0]
    assert not finra_src["skipped"]
    data = finra_src["data"]
    finding = GovernmentRecordsUSFinding(
        subject=_extract_subject(data, "finra-brokercheck"),
        source="finra-brokercheck",
        record_type=_extract_record_type(data, "finra-brokercheck"),
        entity_name="John Smith",
        identifier=_extract_subject(data, "finra-brokercheck"),
        details=_extract_details(data, "finra-brokercheck"),
        raw_evidence=data,
        raw_hash=finra_src["raw_hash"],
        provenance=Provenance(
            tool="government_records_us",
            source_url="sub-source:finra-brokercheck",
            confidence=0.80,
            raw_evidence_sha256=finra_src["raw_hash"],
            adapter_version="1.0",
            notes=["Normalized from finra-brokercheck"],
        ),
    )
    assert finding.subject == "FINRA:1234567:John Smith"
    assert finding.record_type == "broker_check"
    assert finding.entity_name == "John Smith"


# ── run result parsing ─────────────────────────────────────────────────────────


def _request(value: str = "John Smith") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.PERSON_NAME, value=value), legal_only=True
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
            "input_type": "person_name",
            "input_value": "John Smith",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
        }
    )


@parser_test("government_records_us")
def test_parse_success():
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = GovernmentRecordsUSAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 4

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == {
        "finra-brokercheck",
        "bop-inmate-locator",
        "occ-enforcement",
        "fed-enforcement",
    }

    finra = by_source["finra-brokercheck"]
    assert finra.value == "FINRA:1234567:John Smith"
    assert finra.subject == "FINRA:1234567:John Smith"
    assert finra.record_type == "broker_check"
    assert finra.entity_name == "John Smith"
    assert finra.attributes["details"]["crd"] == 1234567
    assert finra.attributes["details"]["registrations"] == 3
    assert finra.attributes["details"]["barred"] is False
    assert finra.attributes["date"] == fixture["sources"][0]["timestamp"][:10]

    bop = by_source["bop-inmate-locator"]
    assert bop.value == "BOP:12345-060:SMITH"
    assert bop.record_type == "inmate_record"
    assert bop.attributes["details"]["count"] == 1

    occ = by_source["occ-enforcement"]
    assert occ.value == "OCC:First National Bank"
    assert occ.record_type == "occ_enforcement"
    assert occ.attributes["details"]["count"] == 1

    fed = by_source["fed-enforcement"]
    assert fed.value == "FED:First National Bank:John Smith"
    assert fed.record_type == "enforcement_action"

    for finding in result.findings:
        assert finding.entity_type == EntityType.GOVERNMENT_RECORD
        assert finding.provenance.tool == "government_records_us"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80
        raw = finding.attributes["raw_evidence"]
        assert raw
        assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
            json.dumps(raw, sort_keys=True).encode()
        ).hexdigest()


def test_parse_skipped():
    """Test that skipped sub-sources produce a finding with skip reason."""
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    payload = _payload(
        [
            _source(
                "sam-gov",
                skipped=True,
                skip_reason="SAM_API_KEY not set",
                http_status=0,
                data=None,
            )
        ]
    )

    adapter = GovernmentRecordsUSAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "sam-gov"
    assert finding.value == "sam-gov:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {
        "skipped": True,
        "reason": "SAM_API_KEY not set",
    }
    assert finding.attributes["raw_evidence"] == {
        "skipped": True,
        "reason": "SAM_API_KEY not set",
    }
    assert "Skipped: SAM_API_KEY not set" in finding.provenance.notes


def test_parse_error():
    """Test that errored sub-sources produce a finding with error info."""
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    payload = _payload(
        [_source("finra-brokercheck", http_status=500, error="Internal Server Error")]
    )

    adapter = GovernmentRecordsUSAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "finra-brokercheck"
    assert finding.value == "finra-brokercheck:error"
    assert finding.attributes["details"] == {
        "error": "Internal Server Error",
        "http_status": 500,
    }
    assert "Error: Internal Server Error" in finding.provenance.notes

    # A sub-source error must not be reported as a successful record.
    assert finding.record_type is None
    assert finding.attributes.get("raw_evidence") == {
        "error": "Internal Server Error",
        "http_status": 500,
    }


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    adapter = GovernmentRecordsUSAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    adapter = GovernmentRecordsUSAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# ── adapter wiring ─────────────────────────────────────────────────────────────


def test_adapter_supports_types():
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    adapter = GovernmentRecordsUSAdapter()
    assert adapter.supports(SeedType.NAME)
    assert adapter.supports(SeedType.COMPANY_NAME)
    assert adapter.supports(SeedType.BANK_NAME)
    assert adapter.supports(SeedType.VIN)
    assert adapter.supports(SeedType.PERSON_NAME)
    assert adapter.supports(SeedType.LOBBYIST_NAME)


def test_adapter_input_types():
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    adapter = GovernmentRecordsUSAdapter()
    # Each seed type should map to a runner input_type
    type_map = {
        SeedType.NAME: "name",
        SeedType.COMPANY_NAME: "company_name",
        SeedType.BANK_NAME: "bank_name",
        SeedType.VIN: "vin",
        SeedType.PERSON_NAME: "person_name",
        SeedType.LOBBYIST_NAME: "lobbyist_name",
    }
    for seed_type, expected in type_map.items():
        # Build a minimal request object
        seed_obj = type("Seed", (), {"type": seed_type, "value": "test_val"})()
        req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
        cmd = adapter.build_command(req, None)
        assert cmd[0] == expected, f"{seed_type}: expected {expected}, got {cmd[0]}"


def test_adapter_build_command_name():
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter
    from aletheia.core.models import SeedType

    adapter = GovernmentRecordsUSAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.NAME, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    cmd = adapter.build_command(req, None)
    assert cmd == ["name", "test_val"]


def test_adapter_build_command_vin():
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter
    from aletheia.core.models import SeedType

    adapter = GovernmentRecordsUSAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.VIN, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    cmd = adapter.build_command(req, None)
    assert cmd == ["vin", "test_val"]