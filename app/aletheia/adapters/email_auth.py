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

# Sub-sources implemented by docker/email_auth/runner.py. One is the keyless
# scan.mx HTTPS JSON API and one is the locally installed checkdmarc library
# (which queries DNS directly). The exact endpoint / module, authentication and
# documented rate limit of each are recorded in docker/email_auth/RATE_LIMITS.md.
SUPPORTED_SUB_SOURCES = (
    "scan-mx",
    "checkdmarc",
)

# Candidates with no verifiable request contract are never queried. Both
# candidates for this batch were verified from their own documentation (the
# scan.mx API page and the checkdmarc API reference), so nothing is dropped and
# this map is empty. The runner still reports any entry added here once per run
# as a skipped source carrying this exact reason; no endpoint, import or version
# is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {}


class EmailAuthFinding(Finding):
    """Normalized email-authentication (MX/SPF/DMARC) finding from any sub-source."""

    # Subject is stored as the Finding.value field, but also exposed directly
    subject: str | None = None
    # Record type and the observed domain/grade are also exposed as direct attributes
    record_type: str | None = None
    domain: str | None = None
    grade: str | None = None
    score: float | None = None
    date: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        domain: str | None = None,
        grade: str | None = None,
        score: float | None = None,
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
        if domain:
            attributes["domain"] = domain
        if grade:
            attributes["grade"] = grade
        if score is not None:
            attributes["score"] = score
        if date:
            attributes["date"] = date
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="email_auth",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            entity_type=EntityType.EMAIL_AUTH_RECORD,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/domain as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.domain = domain
        self.grade = grade
        self.score = score
        self.date = date


def _email_auth_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="email_auth",
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
    "scan-mx": "SCANMX",
    "checkdmarc": "CHECKDMARC",
}

_RECORD_TYPES = {
    "scan-mx": "scan_mx_email_authentication_report",
    "checkdmarc": "checkdmarc_email_authentication_record",
}


def _extract_subject(data: dict, source: str) -> str:
    """Extract a record identifier from the email-authentication payload shapes."""
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


def _extract_domain(data: dict, source: str) -> str | None:
    query = data.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()
    record = _first_record(data, source)
    return record.get("record_id") or None if record else None


def _extract_grade(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    grade = record.get("grade") if record else None
    return grade if isinstance(grade, str) and grade.strip() else None


def _extract_score(data: dict, source: str) -> float | None:
    record = _first_record(data, source)
    score = record.get("score") if record else None
    # bool is an int subclass; a JSON boolean is never a numeric score.
    if isinstance(score, bool):
        return None
    if isinstance(score, (int, float)):
        return float(score)
    return None


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the email-authentication payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return None
    details: dict[str, Any] = {
        "api_source": data.get("api_source"),
        "api_documentation": data.get("api_documentation"),
        "endpoint": data.get("endpoint"),
        "module": data.get("module"),
        "invocation": data.get("invocation"),
        "query": data.get("query"),
        "record_count": data.get("record_count"),
        "truncated": data.get("truncated", False),
        "record_id": record.get("record_id"),
        "detail": record.get("detail"),
    }
    if source == "scan-mx":
        details.update(
            {
                "grade": record.get("grade"),
                "score": record.get("score"),
                "provider": record.get("provider"),
                "email_configured": record.get("email_configured"),
                "smtp_status": record.get("smtp_status"),
                "permalink": record.get("permalink"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "expires_at": record.get("expires_at"),
                "sections": record.get("sections"),
                "checks": record.get("checks"),
                "check_count": data.get("check_count"),
            }
        )
    elif source == "checkdmarc":
        details.update(
            {
                "domain": record.get("domain"),
                "base_domain": record.get("base_domain"),
                "dnssec": record.get("dnssec"),
                "mx": record.get("mx"),
                "spf": record.get("spf"),
                "dmarc": record.get("dmarc"),
            }
        )
    return details


class EmailAuthAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="email_auth",
        license="Composite adapter; sub-sources are the keyless scan.mx email-authentication HTTPS API (https://api.scan.mx/) and the Apache-2.0 checkdmarc library (https://pypi.org/project/checkdmarc/)",
        input_types=[SeedType.DOMAIN],
        output_types=[EntityType.EMAIL_AUTH_RECORD],
        legal_notes=[
            "Composite adapter covering the two verified sub-sources of the email_auth batch: scan-mx (the keyless scan.mx email-authentication and deliverability JSON API) and checkdmarc (the Apache-2.0 checkdmarc Python library, imported as a library and called through its documented checkdmarc.check_domains entry point). Both candidates were verified from their own official documentation, so nothing is dropped and the runner reports no candidate as a skipped source.",
            "Every endpoint, query-parameter name, authentication requirement, documented rate limit, documentation URL and version pin was read from the provider's own official documentation (https://api.scan.mx/ and https://domainaware.github.io/checkdmarc/api.html); none was inferred from an example response. All of them are recorded in docker/email_auth/RATE_LIMITS.md.",
            "The scan.mx API is keyless with no signup and needs no credential. checkdmarc runs inside the image and queries DNS directly. Neither sub-source needs an API key, so the descriptor declares no secret environment variable and no credential is stored in this repository.",
            "The runner classifies the seed as a fully qualified domain name before either sub-source is called: scan.mx documents that a non-FQDN is answered with HTTP 422 invalid_domain and checkdmarc documents domain names, so a value that is not an FQDN is reported as a documented skip instead of being sent.",
            "An email-authentication record is a DNS observation of a domain's published mail configuration, not a statement about the organisation operating it or about its reputation. Both sub-sources are queried at most once per run, so a run contacts a third-party API and third-party DNS resolvers and needs authorisation; the assertion is required.",
        ],
        rate_limit="At most one assessment per implemented sub-source per run (two total): one HTTPS request to the documented scan.mx check endpoint and one checkdmarc.check_domains call. No pagination and no parallel assessments. scan.mx documents that reports are cached for up to 30 days and that the API is rate-limited per IP and per (IP, domain) for abuse prevention, answers HTTP 429 rate_limited with a Retry-After header, and caps forced re-scans of a domain hourly; no numeric request rate is published on its API page. checkdmarc publishes no request limit because it queries DNS directly rather than through a rate-limited API. See docker/email_auth/RATE_LIMITS.md",
        invocation="Keyless scan.mx HTTPS JSON API plus the locally installed checkdmarc library, via dedicated Docker runner (aletheia/email-auth:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/email_auth",
        network_required=True,
        docker_image="aletheia/email-auth:v1",
        output_schema={"finding_type": "EmailAuthFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.DOMAIN}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type
        type_map = {
            SeedType.DOMAIN: "domain",
        }
        input_type = type_map.get(request.seed.type, "domain")
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
                findings.append(EmailAuthFinding(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    record_type=None,
                    domain=None,
                    grade=None,
                    score=None,
                    date=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_email_auth_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(EmailAuthFinding(
                    subject=f"{source_name}:error",
                    source=source_name,
                    record_type=None,
                    domain=None,
                    grade=None,
                    score=None,
                    date=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_email_auth_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)
            domain = _extract_domain(data, source_name) or input_value
            grade = _extract_grade(data, source_name)
            score = _extract_score(data, source_name)

            finding = EmailAuthFinding(
                subject=subject,
                source=source_name,
                record_type=record_type,
                domain=domain,
                grade=grade,
                score=score,
                date=timestamp[:10] if timestamp else None,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_email_auth_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
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
    if name == "EmailAuthAdapter":
        return EmailAuthAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
