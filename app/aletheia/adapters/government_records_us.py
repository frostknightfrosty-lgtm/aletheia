from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor,
    AdapterRunRequest,
    AdapterRunResult,
    EntityType,
    Finding,
    Provenance,
    Seed,
    SeedType,
)


class GovernmentRecordsUSFinding(Finding):
    """Normalized government records finding from any sub-source."""

    # Subject is stored as the Finding.value field, but also exposed directly
    subject: str | None = None
    # Record type and entity name are also exposed as direct attributes
    record_type: str | None = None
    entity_name: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        entity_name: str | None = None,
        identifier: str | None = None,
        location: str | None = None,
        date: str | None = None,
        details: dict[str, Any] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        raw_hash: str | None = None,
        timestamp: str | None = None,
        provenance: Provenance | None = None,
    ):
        attributes = {"source": source}
        if record_type:
            attributes["record_type"] = record_type
        if entity_name:
            attributes["entity_name"] = entity_name
        if identifier:
            attributes["identifier"] = identifier
        if location:
            attributes["location"] = location
        if date:
            attributes["date"] = date
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="government_records_us",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            entity_type=EntityType.GOVERNMENT_RECORD,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/entity_name as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.entity_name = entity_name


def _govrec_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="government_records_us",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _extract_subject(data: dict, source: str) -> str:
    """Extract a subject identifier from various source formats."""
    if source == "finra-brokercheck":
        if isinstance(data.get("data"), list) and data["data"]:
            d = data["data"][0]
            crd = d.get("crd")
            name = f"{d.get('firstName', '')} {d.get('lastName', '')}".strip()
            return f"FINRA:{crd}:{name}" if crd else f"FINRA:{name}"
    if source == "fdic-bankfind":
        if isinstance(data.get("data"), list) and data["data"]:
            d = data["data"][0]
            cert = d.get("CERT")
            name = d.get("NAME", "")
            return f"FDIC:{cert}:{name}" if cert else f"FDIC:{name}"
    if source == "fed-enforcement":
        if isinstance(data.get("results"), list) and data["results"]:
            d = data["results"][0]
            org = d.get("bankingOrganization", "")
            ind = d.get("individual", "")
            return f"FED:{org}:{ind}"
    if source == "occ-enforcement":
        if isinstance(data.get("enforcementActions"), list) and data["enforcementActions"]:
            d = data["enforcementActions"][0]
            bank = d.get("bankName", "")
            return f"OCC:{bank}"
    if source == "usaspending":
        if isinstance(data.get("results"), list) and data["results"]:
            d = data["results"][0]
            return f"USASPENDING:{d.get('recipient_name', '')}:{d.get('recipient_id', '')}"
    if source == "sam-gov":
        if isinstance(data.get("entityData"), list) and data["entityData"]:
            d = data["entityData"][0]
            return f"SAM:{d.get('entityId', '')}:{d.get('entityName', '')}"
    if source == "lda":
        if isinstance(data.get("results"), list) and data["results"]:
            d = data["results"][0]
            return f"LDA:{d.get('clientName', '')}:{d.get('filingUuid', '')}"
    if source == "foia-gov":
        if isinstance(data.get("data"), list) and data["data"]:
            d = data["data"][0]
            return f"FOIA:{d.get('id', '')}:{d.get('name', '')}"
    if source == "nhtsa-vpic":
        if isinstance(data.get("Results"), list) and data["Results"]:
            d = data["Results"][0]
            return f"NHTSA:{d.get('VIN', '')}"
    if source == "bop-inmate-locator":
        if isinstance(data.get("InmateLocator"), list) and data["InmateLocator"]:
            d = data["InmateLocator"][0]
            return f"BOP:{d.get('inmateNum', '')}:{d.get('nameLast', '')}"
    if source == "nyc-open-data":
        if isinstance(data, list) and data:
            d = data[0]
            return f"NYC:{d.get('unique_key', '')}:{d.get('complaint_type', '')}"
    return source


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from various source formats."""
    if source == "finra-brokercheck":
        if isinstance(data.get("data"), list) and data["data"]:
            d = data["data"][0]
            return {
                "crd": d.get("crd"),
                "bc_scope": d.get("bcScope"),
                "ia_scope": d.get("iaScope"),
                "bc_disclosure": d.get("hasBcDisclosure"),
                "has_bc_disclosure": d.get("hasBcDisclosure"),
                "ia_disclosure": d.get("hasIaDisclosure"),
                "barred": d.get("isPermanentlyBarred"),
                "registrations": d.get("approvedFinraRegistrationCount"),
                "employments": d.get("currentEmployments"),
            }
    if source == "fdic-bankfind":
        if isinstance(data.get("data"), list) and data["data"]:
            d = data["data"][0]
            return {k: v for k, v in d.items() if k in ("CERT", "NAME", "STNAME", "CITY", "ACTIVE", "ASSET", "DEP")}
    if source == "fed-enforcement":
        if isinstance(data.get("results"), list):
            return {"count": len(data["results"]), "records": data["results"][:10]}
    if source == "occ-enforcement":
        if isinstance(data.get("enforcementActions"), list):
            return {"count": len(data["enforcementActions"]), "records": data["enforcementActions"][:10]}
    if source == "usaspending":
        if isinstance(data.get("results"), list):
            return {"count": len(data["results"]), "page_meta": data.get("page_metadata", {})}
    if source == "sam-gov":
        if isinstance(data.get("entityData"), list):
            return {"count": len(data["entityData"])}
    if source == "lda":
        if isinstance(data.get("results"), list):
            return {"count": len(data["results"]), "filings": [{"filing_uuid": f.get("filingUuid"), "client": f.get("clientName")} for f in data["results"][:10]]}
    if source == "foia-gov":
        if isinstance(data.get("data"), list):
            return {"count": len(data["data"]), "agencies": [a.get("name") for a in data["data"][:10]]}
    if source == "nhtsa-vpic":
        if isinstance(data.get("Results"), list):
            d = data["Results"][0]
            return {k: v for k, v in d.items() if k in ("VIN", "Make", "Model", "ModelYear", "VehicleType", "BodyClass", "Manufacturer")}
    if source == "bop-inmate-locator":
        if isinstance(data.get("InmateLocator"), list):
            return {"count": len(data["InmateLocator"]), "records": data["InmateLocator"][:5]}
    if source == "nyc-open-data":
        if isinstance(data, list):
            return {"count": len(data), "complaint_types": list(set(d.get("complaint_type") for d in data[:50] if d.get("complaint_type")))}
    return None


def _extract_record_type(data: dict, source: str) -> str | None:
    if source == "finra-brokercheck":
        return "broker_check"
    if source == "fdic-bankfind":
        return "bank_institution"
    if source == "fed-enforcement":
        return "enforcement_action"
    if source == "occ-enforcement":
        return "occ_enforcement"
    if source == "usaspending":
        return "federal_award"
    if source == "sam-gov":
        return "entity_registration"
    if source == "lda":
        return "lobbying_filing"
    if source == "foia-gov":
        return "foia_agency"
    if source == "nhtsa-vpic":
        return "vehicle_specs"
    if source == "bop-inmate-locator":
        return "inmate_record"
    if source == "nyc-open-data":
        return "311_service_request"
    return None


class GovernmentRecordsUSAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="government_records_us",
        license="Composite adapter; sub-sources are US federal/state public data",
        input_types=[SeedType.NAME, SeedType.COMPANY_NAME, SeedType.BANK_NAME, SeedType.VIN, SeedType.PERSON_NAME, SeedType.LOBBYIST_NAME],
        output_types=[EntityType.GOVERNMENT_RECORD],
        legal_notes=[
            "Composite adapter querying 11 US government records sub-sources via their public APIs.",
            "Sub-sources requiring free API keys (OCC, SAM.gov, FOIA.gov) will be skipped if the corresponding environment variable is not set. Skip reasons are recorded in output.",
            "Tier 1 sub-sources (FINRA, FDIC, Federal Reserve, USAspending, LDA anonymous, NHTSA, BOP, NYC Open Data anonymous) run without keys.",
            "All sub-sources are public government data APIs; no unauthorized access, CAPTCHA bypass, or credential use against third-party accounts.",
            "Rate limits are per-sub-source; the adapter queries each at most once per run. Respect provider quotas and 429 responses.",
        ],
        rate_limit="One query per relevant sub-source per run; 11 sub-sources total. Individual limits documented in docker/government_records_us/RATE_LIMITS.md",
        invocation="HTTPS APIs via dedicated Docker runner (aletheia/gov-records-us:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/government_records_us",
        network_required=True,
        docker_image="aletheia/gov-records-us:v1",
        output_schema={"finding_type": "GovernmentRecordsUSFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "OCC_API_KEY",
            "SAM_API_KEY",
            "FOIA_API_KEY",
            "LDA_API_KEY",
            "NYC_OPEN_DATA_TOKEN",
        ],
        parser_test_exempt=True,
        parser_test_exempt_reason="Parser tests in tests/test_government_records_us_adapter.py (25 tests covering all 11 sub-sources and edge cases)",
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.NAME, SeedType.COMPANY_NAME, SeedType.BANK_NAME, SeedType.VIN, SeedType.PERSON_NAME, SeedType.LOBBYIST_NAME}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type
        type_map = {
            SeedType.NAME: "name",
            SeedType.COMPANY_NAME: "company_name",
            SeedType.BANK_NAME: "bank_name",
            SeedType.VIN: "vin",
            SeedType.PERSON_NAME: "person_name",
            SeedType.LOBBYIST_NAME: "lobbyist_name",
        }
        input_type = type_map.get(request.seed.type, "name")
        return [input_type, request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Any, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode("utf-8")
        findings: list[Finding] = []

        if exit_code != 0:
            return AdapterRunResult(
                run_id=request.run_id,
                adapter=self.descriptor,
                status="failed",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=exit_code,
                findings=[],
                stderr_tail=stderr[-4000:],
                stdout_tail=stdout[-4000:],
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return AdapterRunResult(
                run_id=request.run_id,
                adapter=self.descriptor,
                status="partial",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=1,
                findings=[],
                stderr_tail="Runner output was not valid JSON",
                stdout_tail=stdout[-4000:],
            )

        input_type = payload.get("input_type", "")
        input_value = payload.get("input_value", "")
        sources = payload.get("sources", [])

        for src in sources:
            source_name = src.get("source", "unknown")
            skipped = src.get("skipped", False)
            skip_reason = src.get("skip_reason")
            data = src.get("data")
            http_status = src.get("http_status", 0)
            error = src.get("error")
            raw_hash = src.get("raw_hash")
            timestamp = src.get("timestamp")

            if skipped:
                findings.append(GovernmentRecordsUSFinding(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    record_type=None,
                    entity_name=None,
                    identifier=None,
                    location=None,
                    date=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_govrec_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(GovernmentRecordsUSFinding(
                    subject=f"{source_name}:error",
                    source=source_name,
                    record_type=None,
                    entity_name=None,
                    identifier=None,
                    location=None,
                    date=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_govrec_provenance(source_name, json.dumps({"error": error}).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)

            finding = GovernmentRecordsUSFinding(
                subject=subject,
                source=source_name,
                record_type=record_type,
                entity_name=input_value,
                identifier=subject,
                location=None,
                date=timestamp[:10] if timestamp else None,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_govrec_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
            )
            findings.append(finding)

        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )

    def _extract_subject(self, data: dict, source: str) -> str:
        return _extract_subject(data, source)

    def _extract_details(self, data: dict, source: str) -> dict[str, Any] | None:
        return _extract_details(data, source)

    def _extract_record_type(self, data: dict, source: str) -> str | None:
        return _extract_record_type(data, source)


# Auto-register if this module is loaded
def __getattr__(name: str):
    if name == "GovernmentRecordsUSAdapter":
        return GovernmentRecordsUSAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")