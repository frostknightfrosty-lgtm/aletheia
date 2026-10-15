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

# Sub-sources implemented by docker/academic_search/runner.py. Each one is a
# documented search endpoint whose exact query parameter was read from the
# provider's own official documentation (see docker/academic_search/RATE_LIMITS.md
# for the verbatim parameter name, auth method, documented rate limit and docs URL
# of every sub-source).
SUPPORTED_SUB_SOURCES = (
    "openalex",
    "crossref",
    "semantic-scholar",
    "arxiv",
    "core",
    "openaire",
)

# Sub-sources that publish no documented title/keyword/author search and are
# therefore never queried. The runner reports each one once per run as a skipped
# source carrying this exact reason; no URL is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "unpaywall": (
        "Unpaywall documents no title, keyword or author search: its only live endpoint is a DOI lookup "
        "(GET /v2/:doi) and the documented title search (GET /v2/search?query=...) was retired on "
        "18 September 2026 and now returns 410 Gone, so no documented search contract exists for this adapter's "
        "name-based input types."
    ),
}


class AcademicSearchFinding(Finding):
    """Normalized academic record from any academic-search sub-source."""

    # Subject is stored as the Finding.value field, but also exposed directly
    subject: str | None = None
    # Record type, title and DOI are also exposed as direct attributes
    record_type: str | None = None
    title: str | None = None
    doi: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        title: str | None = None,
        doi: str | None = None,
        authors: list[str] | None = None,
        year: int | str | None = None,
        venue: str | None = None,
        identifier: str | None = None,
        url: str | None = None,
        details: dict[str, Any] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        raw_hash: str | None = None,
        timestamp: str | None = None,
        provenance: Provenance | None = None,
    ):
        attributes: dict[str, Any] = {"source": source}
        if record_type:
            attributes["record_type"] = record_type
        if title:
            attributes["title"] = title
        if doi:
            attributes["doi"] = doi
        if authors:
            attributes["authors"] = authors
        if year not in (None, ""):
            attributes["year"] = year
        if venue:
            attributes["venue"] = venue
        if identifier:
            attributes["identifier"] = identifier
        if url:
            attributes["url"] = url
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="academic_search",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            entity_type=EntityType.ACADEMIC_RECORD,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/title as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.title = title
        self.doi = doi


def _academic_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="academic_search",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_record(data: dict, source: str) -> dict[str, Any] | None:
    """Return the first stored record of a sub-source payload, if any.

    The runner only records a payload when the query matched at least one
    scholarly record, so a source with no result contributes no finding rather
    than a negative or empty record.
    """
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None


_SUBJECT_PREFIXES = {
    "openalex": "OPENALEX",
    "crossref": "CROSSREF",
    "semantic-scholar": "SEMANTIC_SCHOLAR",
    "arxiv": "ARXIV",
    "core": "CORE",
    "openaire": "OPENAIRE",
}


def _extract_subject(data: dict, source: str) -> str:
    """Extract a record identifier from the academic search payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return source
    prefix = _SUBJECT_PREFIXES.get(source, source.upper())
    record_id = record.get("record_id")
    title = record.get("title", "")
    return f"{prefix}:{record_id}:{title}" if record_id else f"{prefix}:{title}"


def _extract_record_type(data: dict, source: str) -> str | None:
    if source == "openalex":
        return "openalex_work"
    if source == "crossref":
        return "crossref_work"
    if source == "semantic-scholar":
        return "semantic_scholar_paper"
    if source == "arxiv":
        return "arxiv_preprint"
    if source == "core":
        return "core_work"
    if source == "openaire":
        return "openaire_research_product"
    return None


def _extract_identifier(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    if record is None:
        return None
    return record.get("record_id") or None


def _extract_title(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    return record.get("title") or None if record else None


def _extract_doi(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    return record.get("doi") or None if record else None


def _extract_authors(data: dict, source: str) -> list[str] | None:
    record = _first_record(data, source)
    if record is None:
        return None
    authors = record.get("authors")
    return list(authors) if isinstance(authors, list) and authors else None


def _extract_year(data: dict, source: str) -> int | str | None:
    record = _first_record(data, source)
    return record.get("year") if record else None


def _extract_venue(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    return record.get("venue") or None if record else None


def _extract_url(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    return record.get("url") or None if record else None


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the academic search payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return None
    details: dict[str, Any] = {
        "record_count": data.get("record_count"),
        "truncated": data.get("truncated", False),
        "endpoint": data.get("endpoint"),
        "api_documentation": data.get("api_documentation"),
        "record_id": record.get("record_id"),
        "title": record.get("title"),
        "doi": record.get("doi"),
        "authors": record.get("authors"),
        "year": record.get("year"),
        "venue": record.get("venue"),
        "type": record.get("type"),
    }
    if source == "openalex":
        details.update(
            {
                "cited_by_count": record.get("cited_by_count"),
                "publication_date": record.get("publication_date"),
                "is_oa": record.get("is_oa"),
                "openalex_id": record.get("record_id"),
            }
        )
    elif source == "crossref":
        details.update(
            {
                "publisher": record.get("publisher"),
                "container_title": record.get("venue"),
                "issued": record.get("issued"),
                "member": record.get("member"),
            }
        )
    elif source == "semantic-scholar":
        details.update(
            {
                "venue": record.get("venue"),
                "publication_date": record.get("publication_date"),
                "citation_count": record.get("citation_count"),
                "external_ids": record.get("external_ids"),
            }
        )
    elif source == "arxiv":
        details.update(
            {
                "published": record.get("published"),
                "updated": record.get("updated"),
                "primary_category": record.get("primary_category"),
                "comment": record.get("comment"),
            }
        )
    elif source == "core":
        details.update(
            {
                "publisher": record.get("publisher"),
                "download_url": record.get("download_url"),
                "document_type": record.get("type"),
                "arxiv_id": record.get("arxiv_id"),
            }
        )
    elif source == "openaire":
        details.update(
            {
                "publisher": record.get("publisher"),
                "publication_date": record.get("publication_date"),
                "type": record.get("type"),
            }
        )
    return details


class AcademicSearchAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="academic_search",
        license="Composite adapter; sub-sources are OpenAlex, Crossref, Semantic Scholar Academic Graph, arXiv, CORE API v3 and the OpenAIRE Graph API",
        input_types=[SeedType.NAME, SeedType.COMPANY_NAME, SeedType.PERSON_NAME],
        output_types=[EntityType.ACADEMIC_RECORD],
        legal_notes=[
            "Composite adapter covering the six academic-search sub-sources of the academic_search batch: openalex (OpenAlex works search), crossref (Crossref REST API works query), semantic-scholar (Semantic Scholar Academic Graph paper relevance search), arxiv (arXiv API query), core (CORE API v3 search) and openaire (OpenAIRE Graph API V3 research products search).",
            "Every query parameter was read from the provider's own official documentation; none was inferred from a response example. The verbatim parameter name, auth method, documented rate limit, response format and documentation URL of each sub-source are recorded in docker/academic_search/RATE_LIMITS.md.",
            "unpaywall is deliberately not queried. The Unpaywall REST API documents no title, keyword or author search: its only live endpoint is a DOI lookup and its documented title-search endpoint was retired on 18 September 2026 and now returns 410 Gone. The runner reports it once per run as a skipped source with that exact reason.",
            "A hit is a scholarly-record match on free-text search, not a confirmed identity match between a person or organisation and a publication. Author names are reported exactly as the source published them and must be reviewed by a human before any attribution is relied on.",
            "Only the free-text search parameters documented by each provider are sent. No API key is required for any sub-source and no credential is stored in this repository; the optional keys documented by OpenAlex, Semantic Scholar and CORE are only sent when the matching environment variable is set, and the optional Crossref polite-pool mailto is only sent when CROSSREF_MAILTO is set.",
            "Documented rate limits differ per sub-source and are recorded verbatim in docker/academic_search/RATE_LIMITS.md. The runner issues at most one request per sub-source per run (six requests total) and never paginates.",
        ],
        rate_limit="At most one request per sub-source per run (6 requests per run); no pagination. Documented limits: OpenAlex 10 requests/second without a key and 30/second with a free key; Crossref not published; Semantic Scholar 1000 requests/second shared by all unauthenticated users and 1 request/second introductory for a free key; arXiv a 3 second delay between successive calls; CORE 100 tokens/day and at most 10/minute unauthenticated; OpenAIRE 60 requests/hour unauthenticated and 7200/hour authenticated. See docker/academic_search/RATE_LIMITS.md",
        invocation="HTTPS JSON and Atom XML search APIs via dedicated Docker runner (aletheia/academic-search:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/academic_search",
        network_required=True,
        docker_image="aletheia/academic-search:v1",
        output_schema={"finding_type": "AcademicSearchFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "OPENALEX_API_KEY",
            "SEMANTIC_SCHOLAR_API_KEY",
            "CORE_API_KEY",
            "CROSSREF_MAILTO",
        ],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.NAME, SeedType.COMPANY_NAME, SeedType.PERSON_NAME}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type
        type_map = {
            SeedType.NAME: "name",
            SeedType.COMPANY_NAME: "company_name",
            SeedType.PERSON_NAME: "person_name",
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
                findings.append(AcademicSearchFinding(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    record_type=None,
                    title=None,
                    doi=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_academic_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(AcademicSearchFinding(
                    subject=f"{source_name}:error",
                    source=source_name,
                    record_type=None,
                    title=None,
                    doi=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_academic_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)
            title = _extract_title(data, source_name)
            doi = _extract_doi(data, source_name)
            authors = _extract_authors(data, source_name)
            year = _extract_year(data, source_name)
            venue = _extract_venue(data, source_name)
            url = _extract_url(data, source_name)
            identifier = _extract_identifier(data, source_name)

            finding = AcademicSearchFinding(
                subject=subject,
                source=source_name,
                record_type=record_type,
                title=title,
                doi=doi,
                authors=authors,
                year=year,
                venue=venue,
                identifier=identifier,
                url=url,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_academic_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
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
    if name == "AcademicSearchAdapter":
        return AcademicSearchAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
