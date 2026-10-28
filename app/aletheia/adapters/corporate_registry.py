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

# Sub-sources implemented by docker/corporate_registry/runner.py.
SUPPORTED_SUB_SOURCES = (
    "companies-house",
    "nzbn",
    "kvk-opendata",
    "kvk-zoeken",
    "recherche-entreprises",
)

# Sub-sources with no documented free search API. The runner never fabricates a
# URL for these; it always reports them as skipped with the documented reason.
UNSUPPORTED_SUB_SOURCES = {
    "inpi-rne": "INPI RNE exposes no documented free search API (bulk SFTP and dataset APIs only)",
    "asic": "ASIC publishes no public JSON search API; ASIC Connect is web-only and DSP applications are closed until 2027",
    "cipc": "CIPC provides no public API; enterprise search is web-only",
}


class CorporateRegistryFinding(Finding):
    """Normalized corporate registry finding from any sub-source."""

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
                tool="corporate_registry",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            # Skip/error markers are not domain records (readiness audit 2026-10-25).
            entity_type=EntityType.UNKNOWN if str(subject).endswith((":skipped", ":error")) else EntityType.COMPANY_REGISTRY_RECORD,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/entity_name as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.entity_name = entity_name


def _corpreg_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="corporate_registry",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _extract_subject(data: dict, source: str) -> str:
    """Extract a subject identifier from the various registry payload shapes."""
    if source == "companies-house":
        if isinstance(data.get("items"), list) and data["items"]:
            item = data["items"][0]
            number = item.get("company_number")
            title = item.get("title", "")
            return f"COMPANIES_HOUSE:{number}:{title}" if number else f"COMPANIES_HOUSE:{title}"
    if source == "nzbn":
        if isinstance(data.get("items"), list) and data["items"]:
            item = data["items"][0]
            nzbn = item.get("nzbn")
            name = item.get("entityName", "")
            return f"NZBN:{nzbn}:{name}" if nzbn else f"NZBN:{name}"
    if source == "kvk-opendata":
        number = data.get("kvkNummer")
        name = data.get("naam", "")
        return f"KVK:{number}:{name}" if number else f"KVK:{name}"
    if source == "kvk-zoeken":
        if isinstance(data.get("resultaten"), list) and data["resultaten"]:
            item = data["resultaten"][0]
            number = item.get("kvkNummer")
            name = item.get("naam", "")
            return f"KVK_ZOEKEN:{number}:{name}" if number else f"KVK_ZOEKEN:{name}"
    if source == "recherche-entreprises":
        if isinstance(data.get("results"), list) and data["results"]:
            item = data["results"][0]
            siren = item.get("siren")
            name = item.get("nom_complet", "")
            return f"RNE:{siren}:{name}" if siren else f"RNE:{name}"
    return source


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the various registry payload shapes."""
    if source == "companies-house":
        if isinstance(data.get("items"), list) and data["items"]:
            item = data["items"][0]
            return {
                "total_results": data.get("total_results"),
                "company_number": item.get("company_number"),
                "company_status": item.get("company_status"),
                "company_type": item.get("company_type"),
                "date_of_creation": item.get("date_of_creation"),
                "address_snippet": item.get("address_snippet"),
            }
    if source == "nzbn":
        if isinstance(data.get("items"), list) and data["items"]:
            item = data["items"][0]
            return {
                "total_items": data.get("totalItems"),
                "nzbn": item.get("nzbn"),
                "entity_name": item.get("entityName"),
                "entity_type": item.get("entityType"),
                "entity_status": item.get("entityStatus"),
                "registration_date": item.get("registrationDate"),
            }
    if source == "kvk-opendata":
        if isinstance(data, dict) and data.get("kvkNummer"):
            return {
                "kvk_number": data.get("kvkNummer"),
                "name": data.get("naam"),
                "trade_names": data.get("handelsnamen"),
                "type": data.get("type"),
                "formal_registration_date": data.get("formeleRegistratiedatum"),
                "sbi_codes": [
                    activity.get("sbiCode")
                    for activity in data.get("sbiActiviteiten", [])
                    if isinstance(activity, dict)
                ],
            }
    if source == "kvk-zoeken":
        if isinstance(data.get("resultaten"), list):
            return {
                "count": len(data["resultaten"]),
                "kvk_numbers": [
                    item.get("kvkNummer")
                    for item in data["resultaten"][:10]
                    if isinstance(item, dict)
                ],
            }
    if source == "recherche-entreprises":
        if isinstance(data.get("results"), list) and data["results"]:
            item = data["results"][0]
            siege = item.get("siege") if isinstance(item.get("siege"), dict) else {}
            return {
                "total_results": data.get("total_results"),
                "siren": item.get("siren"),
                "nom_complet": item.get("nom_complet"),
                "activite_principale": item.get("activite_principale"),
                "etat_administratif": item.get("etat_administratif"),
                "date_creation": item.get("date_creation"),
                "siret": siege.get("siret"),
            }
    return None


def _extract_record_type(data: dict, source: str) -> str | None:
    if source == "companies-house":
        return "company_search_result"
    if source == "nzbn":
        return "nz_business_entity"
    if source == "kvk-opendata":
        return "kvk_basisbedrijfsgegevens"
    if source == "kvk-zoeken":
        return "kvk_search_result"
    if source == "recherche-entreprises":
        return "french_company"
    return None


class CorporateRegistryAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="corporate_registry",
        license="Composite adapter; sub-sources are national corporate-registry public data APIs",
        input_types=[SeedType.NAME, SeedType.COMPANY_NAME],
        output_types=[EntityType.COMPANY_REGISTRY_RECORD],
        legal_notes=[
            "Composite adapter querying 8 corporate registry sub-sources: 5 implemented (Companies House, NZBN, KVK Open Dataset, KVK Zoeken, recherche-entreprises) and 3 unsupported (INPI RNE, ASIC, CIPC).",
            "Companies House and NZBN require free API keys; both are skipped, with the skip reason recorded in output, when the corresponding environment variable is not set.",
            "KVK Zoeken is a paid subscription that excludes private use. It is skipped unless KVK_API_KEY is set and is never a default enabled dependency. The free KVK Open Dataset is a number-keyed lookup only.",
            "INPI RNE, ASIC and CIPC publish no free public search API. They are always reported as skipped with their documented reason; no endpoint is fabricated for them.",
            "All sub-sources are public registry data APIs; no unauthorized access, CAPTCHA bypass, or credential use against third-party accounts.",
            "Rate limits are per-sub-source; the adapter queries each at most once per run. Respect provider quotas and 429 responses.",
        ],
        rate_limit="One query per relevant sub-source per run; 8 sub-sources total (5 implemented, 3 unsupported). Individual limits documented in docker/corporate_registry/RATE_LIMITS.md",
        invocation="HTTPS APIs via dedicated Docker runner (aletheia/corp-registry:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/corporate_registry",
        network_required=True,
        docker_image="aletheia/corp-registry:v1",
        output_schema={"finding_type": "CorporateRegistryFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "COMPANIES_HOUSE_API_KEY",
            "NZBN_API_SUBSCRIPTION_KEY",
            "KVK_API_KEY",
        ],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.NAME, SeedType.COMPANY_NAME}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type
        type_map = {
            SeedType.NAME: "name",
            SeedType.COMPANY_NAME: "company_name",
        }
        input_type = type_map.get(request.seed.type, "name")
        return [input_type, request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Any, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
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
                findings.append(CorporateRegistryFinding(
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
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_corpreg_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(CorporateRegistryFinding(
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
                    provenance=_corpreg_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)

            finding = CorporateRegistryFinding(
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
                provenance=_corpreg_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
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
    if name == "CorporateRegistryAdapter":
        return CorporateRegistryAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
