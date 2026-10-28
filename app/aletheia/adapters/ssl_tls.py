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

# Sub-sources implemented by docker/ssl_tls/runner.py. Five of them are local
# command line tools that the image installs (cipherscan is checked out pinned
# by commit, which is the re-review outcome recorded in
# docs/PHASE17_RECHECKS.md #36) and the runner dispatches to by sub-source; one
# is the Qualys SSL Labs assessment API. Every documented
# invocation/endpoint, authentication requirement, documented rate limit, docs
# URL and version pin is recorded in docker/ssl_tls/RATE_LIMITS.md, together
# with the source of each pin.
SUPPORTED_SUB_SOURCES = (
    "qualys-ssl-labs",
    "testssl",
    "certgraph",
    "sslscan",
    "tlsx",
    "cipherscan",
)

# No candidate of this batch is dropped: every sub-source is implemented. The
# mapping is kept so a future candidate that cannot be pinned still lands here
# as an auditable, reasoned skip rather than a silent omission; nobody is in it
# today.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {}


class SslTlsFinding(Finding):
    """Normalized TLS observation from any ssl_tls sub-source."""

    # Subject is stored as the Finding.value field, but also exposed directly
    subject: str | None = None
    # Record type and the record's own detail text are also exposed directly
    record_type: str | None = None
    detail: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        detail: str | None = None,
        target: str | None = None,
        severity: str | None = None,
        tool: str | None = None,
        tool_version: str | None = None,
        invocation: str | None = None,
        details: dict[str, Any] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        raw_hash: str | None = None,
        timestamp: str | None = None,
        provenance: Provenance | None = None,
    ):
        attributes: dict[str, Any] = {"source": source}
        if record_type:
            attributes["record_type"] = record_type
        if detail:
            attributes["detail"] = detail
        if target:
            attributes["target"] = target
        if severity:
            attributes["severity"] = severity
        if tool:
            attributes["tool"] = tool
        if tool_version:
            attributes["tool_version"] = tool_version
        if invocation:
            attributes["invocation"] = invocation
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="ssl_tls",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            # Skip/error markers are not domain records (readiness audit 2026-10-25).
            entity_type=EntityType.UNKNOWN if str(subject).endswith((":skipped", ":error")) else EntityType.TLS_OBSERVATION,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/detail as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.detail = detail


def _ssl_tls_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="ssl_tls",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_record(data: dict, source: str) -> dict[str, Any] | None:
    """Return the first stored record of a sub-source payload, if any.

    The runner only records a payload when the sub-source produced at least one
    observation, so a source with nothing to report contributes no finding
    rather than a negative or empty record.
    """
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None


_SUBJECT_PREFIXES = {
    "qualys-ssl-labs": "SSL_LABS",
    "testssl": "TESTSSL",
    "certgraph": "CERTGRAPH",
    "sslscan": "SSLSCAN",
    "tlsx": "TLSX",
    "cipherscan": "CIPHERSCAN",
}

_RECORD_TYPES = {
    "qualys-ssl-labs": "qualys_ssl_labs_endpoint_assessment",
    "testssl": "testssl_finding",
    "certgraph": "certgraph_domain_node",
    "sslscan": "sslscan_protocol_or_cipher",
    "tlsx": "tlsx_tls_record",
    "cipherscan": "cipherscan_cipher_suite",
}


def _extract_subject(data: dict, source: str) -> str:
    """Extract a subject identifier from the TLS payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return source
    prefix = _SUBJECT_PREFIXES.get(source, source.upper())
    record_id = record.get("record_id")
    detail = record.get("detail", "")
    return f"{prefix}:{record_id}:{detail}" if record_id else f"{prefix}:{detail}"


def _extract_record_type(data: dict, source: str) -> str | None:
    if _first_record(data, source) is None:
        return None
    return _RECORD_TYPES.get(source)


def _extract_detail(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    return record.get("detail") or None if record else None


def _extract_severity(data: dict, source: str) -> str | None:
    record = _first_record(data, source)
    return record.get("severity") or None if record else None


def _extract_target(data: dict, source: str) -> str | None:
    target = data.get("query")
    if isinstance(target, str) and target.strip():
        return target.strip()
    record = _first_record(data, source)
    return record.get("host") or None if record else None


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the TLS payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return None
    details: dict[str, Any] = {
        "record_count": data.get("record_count"),
        "truncated": data.get("truncated", False),
        "endpoint": data.get("endpoint"),
        "api_documentation": data.get("api_documentation"),
        "invocation": data.get("invocation"),
        "source_kind": data.get("source_kind"),
        "tool": data.get("tool"),
        "tool_version": data.get("tool_version"),
        "command": data.get("command"),
        "exit_code": data.get("exit_code"),
        "raw_output_lines": data.get("raw_output_lines"),
        "record_id": record.get("record_id"),
        "detail": record.get("detail"),
        "severity": record.get("severity"),
    }
    if source == "qualys-ssl-labs":
        details.update(
            {
                "assessment_status": data.get("assessment_status"),
                "criteria_version": data.get("criteria_version"),
                "test_time": data.get("test_time"),
                "is_public": data.get("isPublic", data.get("is_public")),
                "status_message": record.get("status_message"),
                "server_name": record.get("server_name"),
                "grade": record.get("grade"),
                "grade_trust_ignored": record.get("grade_trust_ignored"),
                "has_warnings": record.get("has_warnings"),
            }
        )
    elif source == "testssl":
        details.update(
            {
                "cve": record.get("cve"),
                "cwe": record.get("cwe"),
                "ip": record.get("ip"),
                "port": record.get("port"),
                "raw_output_lines": data.get("raw_output_lines"),
            }
        )
    elif source == "certgraph":
        details.update(
            {
                "graph_depth": data.get("graph_depth"),
                "num_domains": data.get("num_domains"),
                "node_type": record.get("node_type"),
                "depth": record.get("depth"),
                "status": record.get("status"),
                "root": record.get("root"),
                "has_dns": record.get("has_dns"),
                "related": record.get("related"),
            }
        )
    elif source == "sslscan":
        details.update(
            {
                "cipher": record.get("cipher"),
                "status": record.get("status"),
                "tls_version": record.get("tls_version"),
                "bits": record.get("bits"),
                "cipher_id": record.get("cipher_id"),
                "strength": record.get("strength"),
                "vulnerable": record.get("vulnerable"),
                "supported": record.get("supported"),
                "secure": record.get("secure"),
            }
        )
    elif source == "tlsx":
        details.update(
            {
                "ip": record.get("ip"),
                "port": record.get("port"),
                "probe_status": record.get("probe_status"),
                "tls_version": record.get("tls_version"),
                "cipher": record.get("cipher"),
                "not_before": record.get("not_before"),
                "not_after": record.get("not_after"),
                "subject_cn": record.get("subject_cn"),
                "subject_org": record.get("subject_org"),
                "sni": record.get("sni"),
            }
        )
    elif source == "cipherscan":
        details.update(
            {
                "protocols": record.get("protocols"),
                "pubkey": record.get("pubkey"),
                "sigalg": record.get("sigalg"),
                "trusted": record.get("trusted"),
                "ticket_hint": record.get("ticket_hint"),
                "ocsp_stapling": record.get("ocsp_stapling"),
                "npn": record.get("npn"),
                "pfs": record.get("pfs"),
                "curves": record.get("curves"),
                "curves_ordering": record.get("curves_ordering"),
                "target": data.get("target"),
                "utctimestamp": data.get("utctimestamp"),
                "serverside": data.get("serverside"),
                "renegotiation": data.get("renegotiation"),
                "compression": data.get("compression"),
                "configs_tested": data.get("configs_tested"),
                "intolerancies_present": data.get("intolerancies_present"),
                "pinned_commit": data.get("pinned_commit"),
            }
        )
    return details


class SslTlsAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="ssl_tls",
        license="Composite adapter; sub-sources are the Qualys SSL Labs assessment API v4, the Debian bookworm testssl.sh and sslscan packages, the CertGraph and tlsx Go modules, and the CipherScan checkout pinned by commit (repository licence MPL-2.0; the checkout ships its own pre-built OpenSSL, with its licence file included)",
        input_types=[SeedType.DOMAIN, SeedType.IP],
        output_types=[EntityType.TLS_OBSERVATION],
        legal_notes=[
            "Composite adapter covering all six verified sub-sources of the ssl_tls batch: qualys-ssl-labs (Qualys SSL Labs assessment API v4), testssl (testssl.sh), certgraph (CertGraph), sslscan, tlsx and cipherscan (CipherScan, pinned by commit; the earlier dropped status was resolved by the 2026-10-18 re-review recorded in docs/PHASE17_RECHECKS.md). No candidate of the batch is dropped, so the runner reports no skipped sub-source.",
            "Five sub-sources are local command line tools installed in the image (CipherScan is checked out at a pinned commit) and invoked as subprocesses with an argv list. No shell string is ever built, so an input value cannot be interpreted as shell syntax. Only the Docker runner dispatches to them; the adapter itself runs nothing locally.",
            "Every documented invocation, endpoint, authentication requirement, documented rate limit, documentation URL and version pin is recorded in docker/ssl_tls/RATE_LIMITS.md, each with the source of its pin. No flag, endpoint or version was inferred from an example response.",
            "The Qualys SSL Labs API v4 analyze call documents a mandatory email request header holding the address registered through the registration API and answers 441 for an unregistered client. The runner sends the header only when SSLLABS_EMAIL is set and otherwise reports the sub-source as a documented skip; the address is never written to the runner output.",
            "A TLS observation is a technical measurement of a service, not a statement about the organisation operating it. Direct probes connect to the target, so a run needs authorisation and the assertion is required; results must be reviewed before any security conclusion is drawn.",
            "sslscan, certgraph, tlsx and cipherscan publish no severity classification, so their records are recorded with severity 'info' rather than an invented rating. Only the severities and letter grades the sources themselves publish (testssl.sh OK/INFO/WARN/LOW/MEDIUM/HIGH/CRITICAL and SSL Labs endpoint grades) are normalized.",
        ],
        rate_limit="At most one assessment per sub-source per run: one API call to the documented SSL Labs analyze endpoint and one local invocation each of testssl, certgraph, sslscan, tlsx and cipherscan. No pagination and no parallel assessments. SSL Labs documents that evaluations take at least 60 seconds, that clients should poll no faster than every 5 seconds and then 10 seconds, that concurrent assessments should be kept to a minimum, and that it may answer 429 (Too Many Requests) when a client submits new assessments too fast; testssl.sh, certgraph, sslscan, tlsx and cipherscan publish no numeric limit. See docker/ssl_tls/RATE_LIMITS.md",
        invocation="Local command line tools (testssl, certgraph, sslscan, tlsx, cipherscan) dispatched by sub-source plus the Qualys SSL Labs assessment API v4, via dedicated Docker runner (aletheia/ssl-tls:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/ssl_tls",
        network_required=True,
        docker_image="aletheia/ssl-tls:v1",
        output_schema={"finding_type": "SslTlsFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=["SSLLABS_EMAIL"],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.DOMAIN, SeedType.IP}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type
        type_map = {
            SeedType.DOMAIN: "domain",
            SeedType.IP: "ip",
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
                findings.append(SslTlsFinding(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    record_type=None,
                    detail=None,
                    target=None,
                    severity=None,
                    tool=None,
                    tool_version=None,
                    invocation=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_ssl_tls_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(SslTlsFinding(
                    subject=f"{source_name}:error",
                    source=source_name,
                    record_type=None,
                    detail=None,
                    target=None,
                    severity=None,
                    tool=None,
                    tool_version=None,
                    invocation=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_ssl_tls_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)
            detail = _extract_detail(data, source_name)
            severity = _extract_severity(data, source_name)
            target = _extract_target(data, source_name) or input_value
            tool = data.get("tool")
            tool_version = data.get("tool_version")
            invocation = data.get("invocation")

            finding = SslTlsFinding(
                subject=subject,
                source=source_name,
                record_type=record_type,
                detail=detail,
                target=target,
                severity=severity,
                tool=tool,
                tool_version=tool_version,
                invocation=invocation,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_ssl_tls_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
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
