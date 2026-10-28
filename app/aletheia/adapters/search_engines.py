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

# Sub-sources implemented by docker/search_engines/runner.py. Two are public
# HTTPS JSON APIs: Marginalia Search (API key in the API-Key header, defaulting
# to the documented public key) and the Common Crawl CDXJ/URL index (no
# authentication). The third, SearXNG, is a self-hosted metasearch engine: it
# is not a public API, so it is operated as a loopback-only instance inside
# this adapter's own container (upstream pinned by commit) and queried over
# the documented JSON search endpoint. The exact endpoint, header/credential,
# documented rate limit, pin and documentation URL of each are recorded in
# docker/search_engines/RATE_LIMITS.md.
SUPPORTED_SUB_SOURCES = (
    "marginalia",
    "common-crawl-index",
    "searxng",
)

# Candidates that cannot be queried are never called. The runner reports each one
# once per run as a skipped source carrying this exact reason; no endpoint,
# parameter name or version is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "google-custom-search": (
        'Google\'s own documentation states verbatim "The Custom Search JSON API is closed to new '
        'customers" and "This API is not available for new customers", with the service '
        "discontinuation on January 1, 2027 "
        "(https://developers.google.com/custom-search/v1/overview). A new deployment cannot register."
    ),
}


class WebSearchResult(Finding):
    """Normalized web-search / web-index finding from any sub-source.

    The plan names this output type "WebSearchResult". No existing EntityType
    described a web-search result record, so EntityType.WEB_SEARCH_RESULT was
    added for this batch, exactly as EntityType.TECHNICAL_FINDING was added for
    code_search.
    """

    subject: str | None = None
    record_type: str | None = None
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    date: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        title: str | None = None,
        url: str | None = None,
        snippet: str | None = None,
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
        if title:
            attributes["title"] = title
        if url:
            attributes["url"] = url
        if snippet:
            attributes["snippet"] = snippet
        if date:
            attributes["date"] = date
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="search_engines",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            # Skip/error markers are not domain records (readiness audit 2026-10-25).
            entity_type=EntityType.UNKNOWN if str(subject).endswith((":skipped", ":error")) else EntityType.WEB_SEARCH_RESULT,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/url as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.title = title
        self.url = url
        self.snippet = snippet
        self.date = date


def _search_engines_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="search_engines",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_record(data: dict, source: str) -> dict[str, Any] | None:
    """Return the first stored record of a sub-source payload, if any.

    The runner only records a payload when the sub-source produced at least one
    result, so a source with nothing to report contributes no finding rather
    than a negative or empty record.
    """
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None


_SUBJECT_PREFIXES = {
    "marginalia": "MARGINALIA",
    "common-crawl-index": "CCINDEX",
    "searxng": "SEARXNG",
}

_RECORD_TYPES = {
    "marginalia": "marginalia_search_result",
    "common-crawl-index": "common_crawl_index_record",
    "searxng": "searxng_search_result",
}


def _extract_subject(data: dict, source: str) -> str:
    """Extract a record identifier from the web-search payload shapes."""
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


def _extract_query(data: dict, source: str) -> str | None:
    query = data.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()
    record = _first_record(data, source)
    return record.get("record_id") or None if record else None


def _extract_url(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    if record is None:
        return None
    url = record.get("url") or record.get("record_id")
    return url if isinstance(url, str) and url.strip() else None


def _extract_title(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    if record is None:
        return None
    title = record.get("title")
    return title if isinstance(title, str) and title.strip() else None


def _extract_snippet(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    if record is None:
        return None
    snippet = record.get("snippet") or record.get("description")
    return snippet if isinstance(snippet, str) and snippet.strip() else None


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the web-search payload shapes."""
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
        "title": record.get("title"),
        "url": record.get("url"),
        "snippet": record.get("snippet"),
    }
    if source == "common-crawl-index":
        details.update(
            {
                "crawl_id": data.get("crawl_id"),
                "crawl_id_source": data.get("crawl_id_source"),
                "urlkey": record.get("urlkey"),
                "timestamp": record.get("timestamp"),
                "mime": record.get("mime"),
                "status": record.get("status"),
                "digest": record.get("digest"),
                "length": record.get("length"),
                "offset": record.get("offset"),
                "filename": record.get("filename"),
            }
        )
    elif source == "marginalia":
        details.update(
            {
                "license": data.get("license"),
                "key_source": data.get("key_source"),
            }
        )
    elif source == "searxng":
        details.update(
            {
                "instance": data.get("instance"),
                "pinned_commit": data.get("pinned_commit"),
                "engines_config": data.get("engines_config"),
                "engines_used": data.get("engines_used"),
                "unresponsive_engines": data.get("unresponsive_engines"),
                "number_of_results": data.get("number_of_results"),
                "engine": record.get("engine"),
            }
        )
    return details


class SearchEnginesAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="search_engines",
        license=(
            "Composite adapter; sub-sources are the Marginalia Search API (content provided under "
            "CC-BY-NC-SA 4.0, non-commercial), the Common Crawl CDXJ/URL index (crawl data free "
            "to access by anyone from anywhere) and a loopback-only SearXNG instance operated from "
            "the pinned upstream commit (SearXNG itself is AGPL-3.0-or-later)"
        ),
        input_types=[SeedType.NAME],
        output_types=[EntityType.WEB_SEARCH_RESULT],
        legal_notes=[
            "Composite adapter covering the three verified sub-sources of the search_engines batch: marginalia (the Marginalia Search API), common-crawl-index (the Common Crawl CDXJ/URL index) and searxng (a loopback-only self-hosted SearXNG instance built from the pinned upstream commit). The remaining candidate, google-custom-search, is dropped and never queried; the runner reports it once per run as a skipped source carrying the documented reason.",
            "Every endpoint, query-parameter name, authentication requirement, documented rate limit and documentation URL of the public APIs was read from the provider's own official documentation (https://about.marginalia-search.com/article/api/ for marginalia, https://commoncrawl.org/get-started for common-crawl-index, https://docs.searxng.org/dev/search_api.html for searxng); none was inferred from an example response. All of them are recorded in docker/search_engines/RATE_LIMITS.md.",
            "searxng is not a public API: it is the upstream SearXNG project installed in this adapter's own image from the exact commit pinned in docker/search_engines/RATE_LIMITS.md and operated as a loopback-only instance for the duration of a run. Its JSON output is an instance-side setting: the search API documentation states that supported formats are defined in settings.yml under search: and that requesting an unset format returns 403 Forbidden, so this adapter's generated instance settings enable json explicitly. The instance's engine set is kept (via the documented use_default_settings keep_only mechanism) to keyless engines enabled by default in the pinned release: duckduckgo, brave and wikipedia.",
            "SearXNG is free/open-source software under AGPL-3.0-or-later; it is operated unmodified from the pinned upstream commit (this adapter ships configuration, not a modified distribution). Live runs route the instance's engine requests through the same egress proxy as every other sub-source, so they are rate-limited and audited like all other outbound requests.",
            "Marginalia carries the API key in the API-Key request header on every request. MARGINALIA_API_KEY is read when set; when it is unset the runner uses the documented public key public, which the API page states cannot create custom filters and often hits a rate limit. A free non-commercial key is available by emailing contact@marginalia-search.com. No key is ever printed or recorded.",
            "Marginalia content is provided under CC-BY-NC-SA 4.0, which is non-commercial: results must not be used commercially and are subject to the licence's attribution and share-alike terms. Common Crawl states that crawl data is free to access by anyone from anywhere.",
            "No sub-source publishes a numeric rate limit, so all three are recorded as not published rather than guessing a number; the runner issues at most one HTTP request per public-API sub-source per run plus one loopback query to the embedded instance, and never paginates. The Common Crawl crawl id is pinned to an explicit crawl (never a wildcard), recorded in docker/search_engines/RATE_LIMITS.md.",
            "A web-search hit or a web-index record is a source observation, not an authoritative record: a search result can be stale, biased, spam or misattributed. Every finding must be reviewed against the published page before it is relied on.",
            "marginalia and common-crawl-index are HTTPS APIs queried at most once per run; searxng is a locally operated instance queried over loopback, whose configured engines make the only additional outbound requests (one query per engine per run, through the same egress proxy in live runs). A run contacts third-party search and web-index services, so it needs authorisation and the assertion is required.",
        ],
        rate_limit=(
            "At most one HTTP request per public-API sub-source per run plus one loopback query to "
            "the embedded SearXNG instance (which fans out to its three configured engines), no "
            "pagination, records truncated at 25. No sub-source publishes a numeric rate limit: the "
            "Marginalia API page only states that the public key \"often hits a rate limit\", Common "
            "Crawl publishes none on https://commoncrawl.org/get-started, and the SearXNG search "
            "API page publishes none, so all are recorded as not published. See "
            "docker/search_engines/RATE_LIMITS.md"
        ),
        invocation="HTTPS JSON search-engine and web-index APIs plus a loopback-only self-hosted instance, via dedicated Docker runner (aletheia/search-engines:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/search_engines",
        network_required=True,
        docker_image="aletheia/search-engines:v1",
        output_schema={"finding_type": "WebSearchResult", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "MARGINALIA_API_KEY",
        ],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.NAME}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type. SeedType.NAME is the existing
        # free-text keyword seed reused here (the same precedent as code_search);
        # no new SeedType was invented.
        type_map = {
            SeedType.NAME: "name",
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
                findings.append(WebSearchResult(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    record_type=None,
                    title=None,
                    url=None,
                    snippet=None,
                    date=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_search_engines_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(WebSearchResult(
                    subject=f"{source_name}:error",
                    source=source_name,
                    record_type=None,
                    title=None,
                    url=None,
                    snippet=None,
                    date=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_search_engines_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)
            query = _extract_query(data, source_name) or input_value
            url = _extract_url(data, source_name)
            title = _extract_title(data, source_name)
            snippet = _extract_snippet(data, source_name)

            finding = WebSearchResult(
                subject=subject,
                source=source_name,
                record_type=record_type,
                title=title,
                url=url,
                snippet=snippet,
                date=timestamp[:10] if timestamp else None,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_search_engines_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
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
    if name == "SearchEnginesAdapter":
        return SearchEnginesAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
