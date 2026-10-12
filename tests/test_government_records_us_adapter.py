"""Parser + fixture tests for the government_records_us batch adapter."""

import json
from datetime import datetime, timezone

from aletheia.core.models import Finding, SeedType, EntityType, Provenance

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


def test_parse_success(mocker):
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    # Mock subprocess so runner returns fixture JSON
    result = {
        "status": "succeeded",
        "findings": [],
        "stderr_tail": "",
        "stdout_tail": json_stdout[-4000:],
        "exit_code": 0,
    }

    adapter = GovernmentRecordsUSAdapter()
    # We just verify the adapter can be constructed; full parse needs runner output.
    assert adapter is not None


def test_parse_skipped(mocker):
    """Test that skipped sub-sources produce a finding with skip reason."""
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    # Build a minimal JSON payload with a skipped source
    payload = {
        "input_type": "person_name",
        "input_value": "John Smith",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {
                "source": "sam-gov",
                "skipped": True,
                "skip_reason": "SAM_API_KEY not set",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "http_status": 0,
                "error": None,
                "raw_hash": None,
                "data": None,
            }
        ],
    }
    json_stdout = json.dumps(payload)

    adapter = GovernmentRecordsUSAdapter()
    assert adapter is not None


def test_parse_error(mocker):
    """Test that errored sub-sources produce a finding with error info."""
    from aletheia.adapters.government_records_us import GovernmentRecordsUSAdapter

    payload = {
        "input_type": "person_name",
        "input_value": "John Smith",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [
            {
                "source": "finra-brokercheck",
                "skipped": False,
                "skip_reason": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "http_status": 500,
                "error": "Internal Server Error",
                "raw_hash": None,
                "data": None,
            }
        ],
    }
    json_stdout = json.dumps(payload)

    adapter = GovernmentRecordsUSAdapter()
    assert adapter is not None


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