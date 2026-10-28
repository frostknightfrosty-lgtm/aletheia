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

# Sub-sources implemented by docker/code_search/runner.py. Debian Code Search is
# the only candidate whose request contract could be verified from the project's
# own OpenAPI specification, so it is the only implemented sub-source. Its exact
# endpoint, query parameters, header authentication and documented rate limit
# are recorded in docker/code_search/RATE_LIMITS.md.
SUPPORTED_SUB_SOURCES = (
    "debian-code-search",
)

# Candidates that cannot be queried are never called. The runner reports each one
# once per run as a skipped source carrying this exact reason; no endpoint,
# parameter name or version is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "gitlab-search": (
        'GitLab\'s own Search API docs state verbatim "Every call to this API requires authentication." '
        "(https://docs.gitlab.com/api/search/), and a live probe of "
        "GET https://gitlab.com/api/v4/search?scope=blobs&search=test returned HTTP 401. "
        "The code-search scope therefore cannot be used without a token, and no token flow is implemented."
    ),
    "publicwww": (
        'PublicWWW\'s own API authentication docs state verbatim "A paid plan is required: without one, '
        'every endpoint except / and /v1/account answers 403 plan_required." '
        "(https://publicwww.com/docs/api/authentication/). A paid-only source is barred by standing rule 4, "
        "so it is not implemented. (Its documented base URL is https://api.publicwww.com with an "
        "Authorization: Bearer header, recorded for context only.)"
    ),
}


class TechnicalFinding(Finding):
    """Normalized technical-surface (source-code search) finding.

    The plan names this output type "TechnicalFinding" and gives it a typed
    "finding_kind" discriminator, so the sub-source record type is carried in
    that field rather than in a per-source finding class.
    """

    subject: str | None = None
    finding_kind: str | None = None
    record_type: str | None = None
    query: str | None = None
    match_mode: str | None = None
    date: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        finding_kind: str | None = None,
        record_type: str | None = None,
        query: str | None = None,
        match_mode: str | None = None,
        date: str | None = None,
        details: dict[str, Any] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        raw_hash: str | None = None,
        timestamp: str | None = None,
        provenance: Provenance | None = None,
    ):
        attributes: dict[str, Any] = {"source": source}
        if finding_kind:
            attributes["finding_kind"] = finding_kind
        if record_type:
            attributes["record_type"] = record_type
        if query:
            attributes["query"] = query
        if match_mode:
            attributes["match_mode"] = match_mode
        if date:
            attributes["date"] = date
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="code_search",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            # Skip/error markers are not domain records (readiness audit 2026-10-25).
            entity_type=EntityType.UNKNOWN if str(subject).endswith((":skipped", ":error")) else EntityType.TECHNICAL_FINDING,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/finding_kind/query as direct attributes for convenience
        self.subject = subject
        self.finding_kind = finding_kind
        self.record_type = record_type
        self.query = query
        self.match_mode = match_mode
        self.date = date


def _code_search_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="code_search",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_record(data: dict, source: str) -> dict[str, Any] | None:
    """Return the first stored record of a sub-source payload, if any.

    The runner only records a payload when the sub-source produced a parseable
    document, so a source with nothing to report contributes no finding rather
    than a negative or empty record.
    """
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None


_SUBJECT_PREFIXES = {
    "debian-code-search": "DCS",
}

_FINDING_KINDS = {
    "debian-code-search": "source_code_search_match",
}

_RECORD_TYPES = {
    "debian-code-search": "debian_code_search_match",
}


def _extract_subject(data: dict, source: str) -> str:
    """Extract a record identifier from the code-search payload shape."""
    record = _first_record(data, source)
    if record is None:
        return source
    prefix = _SUBJECT_PREFIXES.get(source, source.upper())
    record_id = record.get("record_id")
    return f"{prefix}:{record_id}" if record_id else f"{prefix}:{source}"


def _extract_finding_kind(data: dict, source: str) -> str | None:
    if _first_record(data, source) is None:
        return None
    return _FINDING_KINDS.get(source)


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


def _extract_match_mode(data: dict, source: str) -> str | None:
    mode = data.get("match_mode")
    return mode if isinstance(mode, str) and mode.strip() else None


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the code-search payload shape."""
    record = _first_record(data, source)
    if record is None:
        return None
    details: dict[str, Any] = {
        "api_source": data.get("api_source"),
        "api_documentation": data.get("api_documentation"),
        "openapi_specification": data.get("openapi_specification"),
        "endpoint": data.get("endpoint"),
        "invocation": data.get("invocation"),
        "query": data.get("query"),
        "match_mode": data.get("match_mode"),
        "record_count": data.get("record_count"),
        "truncated": data.get("truncated", False),
        "record_id": record.get("record_id"),
        "detail": record.get("detail"),
        "response_type": record.get("response_type"),
    }
    return details


class CodeSearchAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="code_search",
        license="Debian Code Search (DFSG open-source code search over Debian source packages; https://codesearch.debian.net/)",
        input_types=[SeedType.NAME],
        output_types=[EntityType.TECHNICAL_FINDING],
        legal_notes=[
            "Composite adapter covering the single verified sub-source of the code_search batch: debian-code-search (the Debian Code Search JSON API, GET https://codesearch.debian.net/api/v1/search). The two other candidates, gitlab-search and publicwww, are dropped and never queried; the runner reports each one once per run as a skipped source carrying the documented reason.",
            "Every endpoint, query-parameter name, authentication requirement, documented rate limit and documentation URL was read from the project's own OpenAPI specification (https://codesearch.debian.net/openapi.json, title \"Debian Code Search\", version 1.4.0) and the project's own API-key FAQ (https://codesearch.debian.net/apikeys/faq); none was inferred from an example response. All of them are recorded in docker/code_search/RATE_LIMITS.md.",
            "Debian Code Search requires a free personal API key carried in the HTTP header x-dcs-apikey; a key is issued by logging in through salsa.debian.org and downloading it, or by emailing stapelberg@debian.org for a non-personal key. When DEBIAN_CODE_SEARCH_API_KEY is unset the sub-source is reported as a documented skip instead of sending a request the documentation says will be rejected (a keyless request is answered HTTP 403); no credential is stored in this repository and no key is ever printed or recorded.",
            "Debian Code Search publishes no numeric rate limit: the OpenAPI specification states none and the FAQ only explains that keys exist so the service can throttle individual callers. This adapter therefore records the limit as not published and issues at most one request per run.",
            "A source-code match is a published-file hit in a Debian source package, not proof that a person or organisation wrote, owns or operates the code, and a raw pass-through of the API document is not an interpretation of it. Every finding must be reviewed against the published record before it is relied on.",
            "No sub-source is a locally installed tool: the implemented sub-source is an HTTPS JSON API queried at most once per run. A run contacts a third-party code-search service, so it needs authorisation and the assertion is required.",
        ],
        rate_limit="At most one HTTP request per run. Debian Code Search publishes no numeric rate limit: the OpenAPI specification at https://codesearch.debian.net/openapi.json states none, and the API-key FAQ only explains that keys let the service throttle individual callers. See docker/code_search/RATE_LIMITS.md",
        invocation="HTTPS JSON Debian code-search API via dedicated Docker runner (aletheia/code-search:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/code_search",
        network_required=True,
        docker_image="aletheia/code-search:v1",
        output_schema={"finding_type": "TechnicalFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "DEBIAN_CODE_SEARCH_API_KEY",
        ],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.NAME}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type. SeedType.NAME is the existing
        # free-text/string seed reused here; no new SeedType was invented.
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
                findings.append(TechnicalFinding(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    finding_kind=None,
                    record_type=None,
                    query=None,
                    match_mode=None,
                    date=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_code_search_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(TechnicalFinding(
                    subject=f"{source_name}:error",
                    source=source_name,
                    finding_kind=None,
                    record_type=None,
                    query=None,
                    match_mode=None,
                    date=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_code_search_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            finding_kind = _extract_finding_kind(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)
            query = _extract_query(data, source_name) or input_value
            match_mode = _extract_match_mode(data, source_name)

            finding = TechnicalFinding(
                subject=subject,
                source=source_name,
                finding_kind=finding_kind,
                record_type=record_type,
                query=query,
                match_mode=match_mode,
                date=timestamp[:10] if timestamp else None,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_code_search_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
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

    def _extract_finding_kind(self, data: dict, source: str) -> str | None:
        return _extract_finding_kind(data, source)

    def _extract_record_type(self, data: dict, source: str) -> str | None:
        return _extract_record_type(data, source)


# Auto-register if this module is loaded
def __getattr__(name: str):
    if name == "CodeSearchAdapter":
        return CodeSearchAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
