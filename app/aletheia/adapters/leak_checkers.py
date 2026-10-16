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
    "leakix",
    "grayhatwarfare",
)

UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "breachdirectory": (
        "The official BreachDirectory site (https://breachdirectory.org/) returned HTTP 403 during "
        "contract review, and no first-party endpoint, parameter, or response contract could be verified. "
        "This source is not queried until its vendor contract can be reviewed; no route is inferred."
    ),
    "leak-lookup": (
        "Leak-Lookup's Terms of Service limit use to personal security/research and searches for oneself "
        "or people authorized in writing. This adapter request model cannot verify that written "
        "authorization, so the source is not queried. See https://leak-lookup.com/support/terms#use-of-service"
    ),
    "bron-vault": (
        "Broń Vault is a self-hosted application: its README describes deploying its Docker services, "
        "uploading local log archives, and using API-key-authenticated local REST routes; it warns not "
        "to expose the app to public networks. This adapter does not deploy or upload into a separate "
        "operator-owned instance. See https://github.com/ITSEC-Research/bron-vault"
    ),
}


class LeakCheckResult(Finding):
    """Normalized leak-index finding returned by a leak checker sub-source."""

    subject: str | None = None
    source: str | None = None
    record_type: str | None = None
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    details: dict[str, Any] | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        title: str | None = None,
        url: str | None = None,
        snippet: str | None = None,
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
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="leak_checkers",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        super().__init__(
            entity_type=EntityType.BREACH,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        self.subject = subject
        self.source = source
        self.record_type = record_type
        self.title = title
        self.url = url
        self.snippet = snippet
        self.details = details


def _leak_checkers_provenance(source: str, raw: dict[str, Any] | None, notes: list[str]) -> Provenance:
    payload = json.dumps(raw or {}, sort_keys=True).encode()
    return Provenance(
        tool="leak_checkers",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(payload).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_record(data: dict[str, Any], source: str) -> dict[str, Any] | None:
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None


_SUBJECT_PREFIXES = {
    "leakix": "LEAKIX",
    "grayhatwarfare": "GRAYHAT",
}

_RECORD_TYPES = {
    "leakix": "leakix_exposure",
    "grayhatwarfare": "grayhatwarfare_bucket",
}


def _extract_subject(data: dict[str, Any], source: str) -> str:
    record = _first_record(data, source)
    if record is None:
        return source
    prefix = _SUBJECT_PREFIXES.get(source, source.upper())
    value = record.get("record_id") or record.get("subject") or record.get("title")
    return f"{prefix}:{value}" if value else f"{prefix}:{source}"


def _extract_record_type(data: dict[str, Any], source: str) -> str | None:
    if _first_record(data, source) is None:
        return None
    return _RECORD_TYPES.get(source)


def _extract_url(data: dict[str, Any], source: str) -> str | None:
    record = _first_record(data, source)
    if record is None:
        return None
    url = record.get("url") or record.get("record_id")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _extract_title(data: dict[str, Any], source: str) -> str | None:
    record = _first_record(data, source)
    if record is None:
        return None
    title = record.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def _extract_snippet(data: dict[str, Any], source: str) -> str | None:
    record = _first_record(data, source)
    if record is None:
        return None
    snippet = record.get("snippet") or record.get("detail")
    if isinstance(snippet, str) and snippet.strip():
        return snippet.strip()
    return None


def _extract_details(data: dict[str, Any], source: str) -> dict[str, Any] | None:
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
    return details


class LeakCheckersAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="leak_checkers",
        license=(
            "Composite adapter covering LeakIX's leak search API and GrayhatWarfare's bucket-file API. "
            "See each vendor's terms and service documentation before use."
        ),
        input_types=[
            SeedType.EMAIL,
            SeedType.USERNAME,
            SeedType.DOMAIN,
            SeedType.IP,
            SeedType.PHONE,
            SeedType.NAME,
        ],
        output_types=[EntityType.BREACH],
        legal_notes=[
            "LeakIX is queried only through its documented GET /search endpoint with scope=leak, q, page=0, "
            "and the api-key header; its docs specify approximately one request per second. GrayhatWarfare "
            "is queried only through GET /api/v2/files with keywords, limit=25, start=0, and the documented "
            "Bearer token header. No returned file is fetched and no pagination is performed.",
            "BreachDirectory is skipped because its official site returned HTTP 403 during this contract "
            "review, leaving no first-party API contract to verify. Leak-Lookup is skipped because its "
            "Terms of Service require self-search or written authorization, which the adapter cannot "
            "validate. Broń Vault is skipped because its official README describes a self-hosted local-log "
            "application, not a vendor-hosted source; this adapter does not deploy or upload to it.",
        ],
        rate_limit=(
            "At most one HTTP request per supported sub-source per run, never paginates, and caps each "
            "response at 25 records. LeakIX documents approximately 1 request/second. GrayhatWarfare's "
            "registered free plan has account-specific result limits; its API docs cap each page at 1,000, "
            "while this runner requests 25. See docker/leak_checkers/RATE_LIMITS.md."
        ),
        invocation="HTTPS JSON leak-index APIs via dedicated Docker runner (aletheia/leak-checkers:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/leak_checkers",
        network_required=True,
        docker_image="aletheia/leak-checkers:v1",
        output_schema={"finding_type": "LeakCheckResult", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=["LEAKIX_API_KEY", "GRAYHATWARFARE_TOKEN"],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {
            SeedType.EMAIL,
            SeedType.USERNAME,
            SeedType.DOMAIN,
            SeedType.IP,
            SeedType.PHONE,
            SeedType.NAME,
        }

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        type_map = {
            SeedType.EMAIL: "email",
            SeedType.USERNAME: "username",
            SeedType.DOMAIN: "domain",
            SeedType.IP: "ip",
            SeedType.PHONE: "phone",
            SeedType.NAME: "keyword",
        }
        input_type = type_map.get(request.seed.type, "keyword")
        return [input_type, request.seed.value]

    def parse(
        self,
        request: AdapterRunRequest,
        workspace: Any,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> AdapterRunResult:
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
        for source_payload in payload.get("sources", []):
            source_name = source_payload.get("source", "unknown")
            skipped = source_payload.get("skipped", False)
            skip_reason = source_payload.get("skip_reason")
            data = source_payload.get("data")
            http_status = source_payload.get("http_status", 0)
            error = source_payload.get("error")
            timestamp = source_payload.get("timestamp")
            raw_hash = source_payload.get("raw_hash")

            if skipped:
                findings.append(
                    LeakCheckResult(
                        subject=f"{source_name}:skipped",
                        source=source_name,
                        details={"skipped": True, "reason": skip_reason},
                        raw_evidence={"skipped": True, "reason": skip_reason},
                        raw_hash=raw_hash,
                        timestamp=timestamp,
                        provenance=_leak_checkers_provenance(
                            source_name,
                            {"skipped": True, "reason": skip_reason},
                            [f"Skipped: {skip_reason}"],
                        ),
                    )
                )
                continue

            if error:
                findings.append(
                    LeakCheckResult(
                        subject=f"{source_name}:error",
                        source=source_name,
                        details={"error": error, "http_status": http_status},
                        raw_evidence={"error": error, "http_status": http_status},
                        raw_hash=raw_hash,
                        timestamp=timestamp,
                        provenance=_leak_checkers_provenance(
                            source_name,
                            {"error": error, "http_status": http_status},
                            [f"Error: {error}"],
                        ),
                    )
                )
                continue

            if not isinstance(data, dict):
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            url = _extract_url(data, source_name)
            title = _extract_title(data, source_name)
            snippet = _extract_snippet(data, source_name)
            details = _extract_details(data, source_name)

            findings.append(
                LeakCheckResult(
                    subject=subject,
                    source=source_name,
                    record_type=record_type,
                    title=title,
                    url=url,
                    snippet=snippet,
                    details=details,
                    raw_evidence=data,
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_leak_checkers_provenance(
                        source_name,
                        data,
                        [f"Normalized from {source_name}", f"Query value={input_value}"],
                    ),
                )
            )

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


# Auto-register if this module is loaded.
def __getattr__(name: str):
    if name == "LeakCheckersAdapter":
        return LeakCheckersAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
