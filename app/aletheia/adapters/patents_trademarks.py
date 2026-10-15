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

# Sub-sources implemented by docker/patents_trademarks/runner.py. Every one is an
# HTTPS API; the exact endpoint, query-parameter names, authentication and
# documented rate limit of each are recorded in docker/patents_trademarks/RATE_LIMITS.md.
SUPPORTED_SUB_SOURCES = (
    "uspto-open-data",
    "uspto-patent-assignment",
    "uspto-tsdr",
    "epo-ops",
)

# Candidates with no verifiable request contract are never queried. The runner
# reports each one once per run as a skipped source carrying this exact reason;
# no endpoint, import or version is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "patentsview": (
        "The PatentsView Search API host does not exist: search.patentsview.org returns NXDOMAIN from the "
        "system resolver and from 1.1.1.1 and 8.8.8.8, and the legacy hosts api.patentsview.org and "
        "patentsview.org now serve the USPTO Open Data Portal single-page application instead of any "
        "PatentsView API reference. The legacy PatentsView API was retired and no reachable PatentsView "
        "request contract exists, so no endpoint or parameter is invented for it."
    ),
    "google-patents-bigquery": (
        "The Google Patents public dataset is reachable only through BigQuery, which requires a Google Cloud "
        "project authenticated with Application Default Credentials or a service-account key plus the "
        "google-cloud-bigquery client library; Google documents no unauthenticated or free-key HTTP path to "
        "bigquery-public-data.google_patents. The runner uses the Python standard library only, so the "
        "candidate is dropped rather than adding a third-party dependency."
    ),
    "euipo-esearch-plus": (
        "EUIPO exposes its trademark and design APIs only through the EUIPO API Portal, which requires an "
        "account, a sandbox access request and a separate production-access application under the EUIPO "
        "conditions of use; there is no free-key or unauthenticated search endpoint. The older eSearch "
        "plus/copla endpoints reset the connection (WinError 10054) and the EUIPO API page answered HTTP 403, "
        "so the request contract cannot be verified and the approval path cannot be completed here."
    ),
}

# The batch plan assigns five sub-sources to patents_trademarks. The composite also
# absorbs EPO OPS and Google Patents from the plan's separate research_discovery row;
# that overlap is recorded in docker/patents_trademarks/RATE_LIMITS.md and in the
# manifest note.
RESEARCH_DISCOVERY_OVERLAP = ("epo-ops", "google-patents-bigquery")


class PatentsTrademarksFinding(Finding):
    """Normalized patent / trademark finding from any sub-source."""

    # Subject is stored as the Finding.value field, but also exposed directly
    subject: str | None = None
    # Record type and the observed identifier are also exposed as direct attributes
    record_type: str | None = None
    identifier: str | None = None
    jurisdiction: str | None = None
    ip_kind: str | None = None
    date: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        identifier: str | None = None,
        jurisdiction: str | None = None,
        ip_kind: str | None = None,
        date: str | None = None,
        details: dict[str, Any] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        raw_hash: str | None = None,
        timestamp: str | None = None,
        provenance: Provenance | None = None,
    ):
        attributes: dict[str, Any] = {"source": source}
        if record_type:
            attributes["record_type"] = record_type
        if identifier:
            attributes["identifier"] = identifier
        if jurisdiction:
            attributes["jurisdiction"] = jurisdiction
        if ip_kind:
            attributes["ip_kind"] = ip_kind
        if date:
            attributes["date"] = date
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="patents_trademarks",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            entity_type=EntityType.INTELLECTUAL_PROPERTY_RECORD,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/identifier as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.identifier = identifier
        self.jurisdiction = jurisdiction
        self.ip_kind = ip_kind
        self.date = date


def _patents_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="patents_trademarks",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_record(data: dict, source: str) -> dict[str, Any] | None:
    """Return the first stored record of a sub-source payload, if any.

    The runner only records a payload when the sub-source produced at least one
    record, so a source with nothing to report contributes no finding rather
    than a negative or empty record.
    """
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None


_SUBJECT_PREFIXES = {
    "uspto-open-data": "USPTO_ODP",
    "uspto-patent-assignment": "USPTO_ASSIGNMENT",
    "uspto-tsdr": "USPTO_TSDR",
    "epo-ops": "EPO",
}

_RECORD_TYPES = {
    "uspto-open-data": "uspto_open_data_patent_application",
    "uspto-patent-assignment": "uspto_patent_assignment",
    "uspto-tsdr": "uspto_tsdr_trademark_case",
    "epo-ops": "epo_ops_publication",
}

_JURISDICTIONS = {
    "uspto-open-data": "US",
    "uspto-patent-assignment": "US",
    "uspto-tsdr": "US",
    "epo-ops": "EP",
}

_IP_KINDS = {
    "uspto-open-data": "patent",
    "uspto-patent-assignment": "patent",
    "uspto-tsdr": "trademark",
    "epo-ops": "patent",
}


def _extract_subject(data: dict, source: str) -> str:
    """Extract a record identifier from the patent / trademark payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return source
    prefix = _SUBJECT_PREFIXES.get(source, source.upper())
    record_id = record.get("record_id")
    return f"{prefix}:{record_id}" if record_id else f"{prefix}:{source}"


def _extract_record_type(data: dict, source: str) -> str | None:
    if _first_record(data, source) is None:
        return None
    return _RECORD_TYPES.get(source)


def _extract_identifier(data: dict, source: str) -> str | None:
    query = data.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()
    record = _first_record(data, source)
    return record.get("record_id") or None if record else None


def _extract_jurisdiction(source: str) -> str | None:
    return _JURISDICTIONS.get(source)


def _extract_ip_kind(source: str) -> str | None:
    return _IP_KINDS.get(source)


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the patent / trademark payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return None
    details: dict[str, Any] = {
        "api_source": data.get("api_source"),
        "api_documentation": data.get("api_documentation"),
        "endpoint": data.get("endpoint"),
        "invocation": data.get("invocation"),
        "query": data.get("query"),
        "record_count": data.get("record_count"),
        "truncated": data.get("truncated", False),
        "record_id": record.get("record_id"),
        "detail": record.get("detail"),
    }
    if source == "uspto-open-data":
        details.update(
            {
                "application_number": record.get("application_number"),
                "patent_number": record.get("patent_number"),
                "invention_title": record.get("invention_title"),
                "application_filing_date": record.get("application_filing_date"),
                "grant_date": record.get("grant_date"),
                "application_status_code": record.get("application_status_code"),
                "application_status_date": record.get("application_status_date"),
                "application_type_label_name": record.get("application_type_label_name"),
                "inventors": record.get("inventors"),
                "applicants": record.get("applicants"),
            }
        )
    elif source == "uspto-patent-assignment":
        details.update(
            {
                "application_number": data.get("application_number") or record.get("application_number"),
                "assignment": record.get("assignment"),
            }
        )
    elif source == "uspto-tsdr":
        details.update(
            {
                "application_number": record.get("application_number"),
                "registration_number": record.get("registration_number"),
                "mark_verbal_element_text": record.get("mark_verbal_element_text"),
                "status_description": record.get("status_description"),
                "status_date": record.get("status_date"),
                "filing_date": record.get("filing_date"),
                "case_status_data": record.get("case_status_data"),
            }
        )
    elif source == "epo-ops":
        details.update(
            {
                "total_result_count": data.get("total_result_count"),
                "country": record.get("country"),
                "doc_number": record.get("doc_number"),
                "kind": record.get("kind"),
            }
        )
    return details


class PatentsTrademarksAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="patents_trademarks",
        license="Composite adapter; sub-sources are the USPTO Open Data Portal API, the USPTO Trademark Status and Document Retrieval (TSDR) API and the EPO Open Patent Services (OPS) API",
        input_types=[SeedType.INTELLECTUAL_PROPERTY],
        output_types=[EntityType.INTELLECTUAL_PROPERTY_RECORD],
        legal_notes=[
            "Composite adapter covering the four verified sub-sources of the patents_trademarks batch: uspto-open-data (USPTO Open Data Portal Patent Search API), uspto-patent-assignment (USPTO Open Data Portal patent application assignment data), uspto-tsdr (USPTO Trademark Status and Document Retrieval API) and epo-ops (EPO Open Patent Services published-data search).",
            "The batch plan assigns five sub-sources to this batch and the composite additionally absorbs EPO OPS and Google Patents from the plan's separate research_discovery row. Three candidates are dropped and never queried: patentsview (its documented host no longer resolves and the legacy domain now serves the USPTO Open Data Portal), google-patents-bigquery (BigQuery requires a Google Cloud project and a third-party client library) and euipo-esearch-plus (EUIPO API access requires an approval process with no free-key or unauthenticated contract). Each is reported once per run as a skipped source carrying the documented reason. The research_discovery overlap is recorded in docker/patents_trademarks/RATE_LIMITS.md and in the manifest note.",
            "Every endpoint, query-parameter name, authentication requirement, documented rate limit and documentation URL was read from the provider's own official documentation or confirmed against the live provider endpoint; none was inferred from an example response. All of them are recorded in docker/patents_trademarks/RATE_LIMITS.md.",
            "uspto-open-data and uspto-patent-assignment require a free USPTO Open Data Portal API key and uspto-tsdr requires a free USPTO TSDR API key; when the matching environment variable is unset the sub-source is reported as a documented skip instead of sending a request the documentation says will be rejected. epo-ops requires a free EPO OPS consumer key and secret and is skipped the same way. No credential is stored in this repository and no key is ever printed or recorded in the runner output.",
            "uspto-tsdr documents trademark serial numbers and uspto-patent-assignment documents patent application numbers, so each is skipped with a recorded reason when the seed is not numeric; a patent application number and a trademark serial are both numeric, so a numeric seed may be sent to more than one US endpoint and a non-matching endpoint simply records no finding.",
            "No sub-source is a locally installed tool, so nothing is executed locally: every sub-source is an HTTPS API queried at most once per run. A run contacts third-party patent and trademark registries, so it needs authorisation and the assertion is required.",
        ],
        rate_limit="At most one HTTP request per implemented sub-source per run (four requests total, plus one EPO OPS OAuth token request), no pagination, records truncated at 25. Documented limits: USPTO Open Data Portal per-key limits are enforced and answered with HTTP 429 but no numeric value is retrievable from a reachable official page (recorded as not published); USPTO TSDR 60 requests per API key per minute for status endpoints and 4 requests per API key per minute for PDF/ZIP downloads (120 and 12 off peak from 10 p.m. to 5 a.m. EST); EPO OPS no requests-per-second number is published and the fair-use policy governs (a keyless request is answered HTTP 403 \"violation of Fair Use policy\"). See docker/patents_trademarks/RATE_LIMITS.md",
        invocation="HTTPS patent and trademark APIs via dedicated Docker runner (aletheia/patents-trademarks:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/patents_trademarks",
        network_required=True,
        docker_image="aletheia/patents-trademarks:v1",
        output_schema={"finding_type": "PatentsTrademarksFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "USPTO_ODP_API_KEY",
            "USPTO_TSDR_API_KEY",
            "EPO_OPS_CONSUMER_KEY",
            "EPO_OPS_CONSUMER_SECRET",
        ],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.INTELLECTUAL_PROPERTY}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type
        type_map = {
            SeedType.INTELLECTUAL_PROPERTY: "intellectual_property",
        }
        input_type = type_map.get(request.seed.type, "intellectual_property")
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
                findings.append(PatentsTrademarksFinding(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    record_type=None,
                    identifier=None,
                    jurisdiction=None,
                    ip_kind=None,
                    date=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_patents_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(PatentsTrademarksFinding(
                    subject=f"{source_name}:error",
                    source=source_name,
                    record_type=None,
                    identifier=None,
                    jurisdiction=None,
                    ip_kind=None,
                    date=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_patents_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)
            identifier = _extract_identifier(data, source_name) or input_value
            jurisdiction = _extract_jurisdiction(source_name)
            ip_kind = _extract_ip_kind(source_name)

            finding = PatentsTrademarksFinding(
                subject=subject,
                source=source_name,
                record_type=record_type,
                identifier=identifier,
                jurisdiction=jurisdiction,
                ip_kind=ip_kind,
                date=timestamp[:10] if timestamp else None,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_patents_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
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
    if name == "PatentsTrademarksAdapter":
        return PatentsTrademarksAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
