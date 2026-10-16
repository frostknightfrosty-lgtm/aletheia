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
    SeedType,
)


SUPPORTED_SUB_SOURCES = (
    "faa-aircraft-registration",
    "openrailwaymap",
    "planespotters",
)

UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "imo-gisis": (
        "IMO documents the Ship and Company Particulars module as a public browser search, but no "
        "public machine-readable request contract or API was found in the official GISIS material. "
        "The adapter does not automate the browser portal or invent a hidden endpoint. See "
        "https://www.imo.org/en/mediacentre/pages/whatsnew-1704.aspx and "
        "https://gisis.imo.org/Public/Default.aspx."
    ),
    "eratv": (
        "ERA's official Knowledge Graph coverage page marks ERATV migration as ongoing, so the public "
        "SPARQL service is not a verified ERATV data endpoint yet. The ERATV browser interface also "
        "uses CAPTCHA after repeated public view/export attempts; the adapter does not automate or "
        "bypass that challenge. See https://www.era.europa.eu/cs/node/1665 and "
        "https://www.era.europa.eu/system/files/2022-11/eratv_usm_deployment_end-user_support_material_user_manual_nas_en.pdf."
    ),
    "eris": (
        "No official railway asset registry or public endpoint corresponding to the name ERIS was "
        "identified in the reviewed ERA sources. The batching plan names ERATV, not ERIS; no endpoint "
        "is inferred from the ambiguous acronym. See https://www.era.europa.eu/cs/node/1665."
    ),
}

_SOURCE_DOCS = {
    "faa-aircraft-registration": "https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download/index.cfm",
    "openrailwaymap": "https://github.com/OpenRailwayMap/OpenRailwayMap-api/blob/master/README.md",
    "planespotters": "https://www.planespotters.net/legal/termsofuse?desktop=true",
    "imo-gisis": "https://gisis.imo.org/Public/Default.aspx",
    "eratv": "https://www.era.europa.eu/cs/node/1665",
    "eris": "https://www.era.europa.eu/cs/node/1665",
}


class TransportAssetFinding(Finding):
    """Normalized source observation about a registered transport asset."""

    subject: str | None = None
    record_type: str | None = None
    registration: str | None = None
    name: str | None = None
    manufacturer: str | None = None
    model_code: str | None = None
    year_manufactured: str | None = None
    status_code: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        registration: str | None = None,
        name: str | None = None,
        manufacturer: str | None = None,
        model_code: str | None = None,
        year_manufactured: str | None = None,
        status_code: str | None = None,
        details: dict[str, Any] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        provenance: Provenance | None = None,
    ) -> None:
        attributes: dict[str, Any] = {"source": source}
        optional = {
            "record_type": record_type,
            "registration": registration,
            "name": name,
            "manufacturer": manufacturer,
            "model_code": model_code,
            "year_manufactured": year_manufactured,
            "status_code": status_code,
        }
        attributes.update({key: value for key, value in optional.items() if value is not None})
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            encoded = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="transport_asset_registry",
                source_url=_SOURCE_DOCS.get(source, "https://www.faa.gov/"),
                confidence=0.80,
                raw_evidence_sha256=hashlib.sha256(encoded).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        super().__init__(
            entity_type=EntityType.TRANSPORT_ASSET_RECORD,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        self.subject = subject
        self.record_type = record_type
        self.registration = registration
        self.name = name
        self.manufacturer = manufacturer
        self.model_code = model_code
        self.year_manufactured = year_manufactured
        self.status_code = status_code


def _provenance(source: str, data: dict[str, Any], notes: list[str]) -> Provenance:
    encoded = json.dumps(data, sort_keys=True).encode()
    return Provenance(
        tool="transport_asset_registry",
        source_url=str(data.get("endpoint") or _SOURCE_DOCS.get(source)),
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(encoded).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


class TransportAssetRegistryAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="transport_asset_registry",
        license=(
            "Composite adapter: FAA public aircraft registration data; OpenStreetMap / "
            "OpenRailwayMap facility data (ODbL); and Planespotters public aircraft-photo metadata."
        ),
        input_types=[SeedType.NAME],
        output_types=[EntityType.TRANSPORT_ASSET_RECORD],
        legal_notes=[
            "The adapter queries at most one public source request per supported input/source. FAA lookups use an N-number only and retain aircraft metadata, never registrant names or addresses. OpenRailwayMap queries one named facility or UIC reference, uses a unique contact-bearing User-Agent, observes its low-volume restrictions, and stops on HTTP 429. Planespotters metadata is limited to photo id, photographer, and source-page link; image files are never downloaded.",
            "IMO GISIS, ERATV, and the ambiguous ERIS candidate are recorded as non-querying skips with evidence-based reasons in docker/transport_asset_registry/RATE_LIMITS.md. The adapter does not automate a CAPTCHA or use an undocumented GISIS endpoint.",
            "A registry record or photo reference is a source observation, not proof of ownership, current operation, or a person's identity. FAA registrant identity and address fields are deliberately not emitted.",
        ],
        rate_limit=(
            "At most one request to each applicable implemented source per run. OpenRailwayMap is limited "
            "to one end-user facility query, uses a five-second timeout, and is not retried after 429. "
            "FAA provides a daily refreshed 60 MB archive; see docker/transport_asset_registry/RATE_LIMITS.md."
        ),
        invocation="FAA CSV download and public HTTPS JSON APIs via dedicated Docker runner (aletheia/transport-asset-registry:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/transport_asset_registry",
        network_required=True,
        docker_image="aletheia/transport-asset-registry:v1",
        output_schema={"finding_type": "TransportAssetFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.NAME

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        if not self.supports(request.seed.type):
            raise ValueError(f"Unsupported seed type for transport_asset_registry: {request.seed.type}")
        return ["name", request.seed.value]

    def parse(
        self,
        request: AdapterRunRequest,
        workspace: Any,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
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

        findings: list[Finding] = []
        for source_result in payload.get("sources", []):
            if not isinstance(source_result, dict):
                continue
            source = str(source_result.get("source", "unknown"))
            if source_result.get("skipped"):
                reason = str(source_result.get("skip_reason") or "Source skipped")
                raw = {"skipped": True, "reason": reason}
                findings.append(
                    TransportAssetFinding(
                        subject=f"{source}:skipped",
                        source=source,
                        details=raw,
                        raw_evidence=raw,
                        provenance=_provenance(source, raw, [f"Skipped: {reason}"]),
                    )
                )
                continue
            if source_result.get("error"):
                raw = {
                    "error": source_result["error"],
                    "http_status": source_result.get("http_status", 0),
                }
                findings.append(
                    TransportAssetFinding(
                        subject=f"{source}:error",
                        source=source,
                        details=raw,
                        raw_evidence=raw,
                        provenance=_provenance(source, raw, [f"Source error: {raw['error']}"]),
                    )
                )
                continue
            data = source_result.get("data")
            if not isinstance(data, dict):
                continue
            records = data.get("records")
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                identifier = str(record.get("record_id") or record.get("registration") or request.seed.value)
                findings.append(
                    TransportAssetFinding(
                        subject=f"{source}:{identifier}",
                        source=source,
                        record_type=str(record.get("record_type") or "transport_asset_observation"),
                        registration=record.get("registration"),
                        name=record.get("name"),
                        manufacturer=record.get("manufacturer"),
                        model_code=record.get("model_code"),
                        year_manufactured=record.get("year_manufactured"),
                        status_code=record.get("status_code"),
                        details={key: value for key, value in record.items() if key not in {
                            "record_id", "registration", "name", "manufacturer", "model_code",
                            "year_manufactured", "status_code", "record_type",
                        }},
                        raw_evidence=record,
                        provenance=_provenance(source, record, [f"Normalized from {source}"]),
                    )
                )
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=0,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )
