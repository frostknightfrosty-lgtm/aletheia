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

# Sub-sources implemented by docker/sanctions_enforcement_watchlists/runner.py.
# Each one publishes a bulk XML artefact that the runner downloads once per run
# and filters locally; none of them offers a JSON search API.
SUPPORTED_SUB_SOURCES = (
    "uk-sanctions-list",
    "swiss-seco",
    "eu-consolidated-sanctions",
)

# Sub-sources with no documented machine-readable public artefact. The runner
# never fabricates a URL for these; it always reports them as skipped with the
# documented reason. All three sub-sources above were verified against their own
# official publication pages, so this map is currently empty.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {}

# The batch plan assigns six sub-sources to sanctions_enforcement_watchlists.
# Three of them (finra-brokercheck, fed-enforcement, occ-enforcement) are already
# implemented inside app/aletheia/adapters/government_records_us.py and are
# deliberately not duplicated here; this adapter covers only the three
# government sanctions-list sub-sources that had no implementation.
IMPLEMENTED_ELSEWHERE = {
    "finra-brokercheck": "government_records_us",
    "fed-enforcement": "government_records_us",
    "occ-enforcement": "government_records_us",
}


class SanctionsEnforcementWatchlistsFinding(Finding):
    """Normalized sanctions / watchlist finding from any sub-source."""

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
        jurisdiction: str | None = None,
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
        if jurisdiction:
            attributes["jurisdiction"] = jurisdiction
        if date:
            attributes["date"] = date
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="sanctions_enforcement_watchlists",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            # Skip/error markers are not domain records (readiness audit 2026-10-25).
            entity_type=EntityType.UNKNOWN if str(subject).endswith((":skipped", ":error")) else EntityType.SANCTION,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/entity_name as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.entity_name = entity_name


def _sanctions_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="sanctions_enforcement_watchlists",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_match(data: dict, source: str) -> dict[str, Any] | None:
    """Return the first stored match of a sub-source payload, if any.

    The runner only records a payload when the query matched at least one listed
    name, so a source with no match contributes no finding rather than a
    negative or empty record.
    """
    matches = data.get("matches")
    if isinstance(matches, list) and matches and isinstance(matches[0], dict):
        return matches[0]
    return None


def _extract_subject(data: dict, source: str) -> str:
    """Extract a subject identifier from the sanctions list payload shapes."""
    match = _first_match(data, source)
    if match is None:
        return source
    if source == "uk-sanctions-list":
        unique_id = match.get("unique_id")
        name = match.get("primary_name", "")
        return f"UK_SANCTIONS:{unique_id}:{name}" if unique_id else f"UK_SANCTIONS:{name}"
    if source == "swiss-seco":
        ssid = match.get("ssid")
        name = match.get("primary_name", "")
        return f"SECO:{ssid}:{name}" if ssid else f"SECO:{name}"
    if source == "eu-consolidated-sanctions":
        reference = match.get("eu_reference_number")
        name = match.get("primary_name", "")
        return f"EU_SANCTIONS:{reference}:{name}" if reference else f"EU_SANCTIONS:{name}"
    return source


def _extract_record_type(data: dict, source: str) -> str | None:
    if source == "uk-sanctions-list":
        return "uk_sanctions_designation"
    if source == "swiss-seco":
        return "swiss_seco_sanctions_target"
    if source == "eu-consolidated-sanctions":
        return "eu_financial_sanctions_designation"
    return None


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the sanctions list payload shapes."""
    match = _first_match(data, source)
    if match is None:
        return None
    details: dict[str, Any] = {
        "match_count": data.get("match_count"),
        "truncated": data.get("truncated", False),
        "list_url": data.get("list_url"),
        "matched_names": match.get("matched_names"),
    }
    if source == "uk-sanctions-list":
        details.update(
            {
                "date_generated": data.get("date_generated"),
                "unique_id": match.get("unique_id"),
                "ofsi_group_id": match.get("ofsi_group_id"),
                "subject_kind": match.get("subject_kind"),
                "regime_name": match.get("regime_name"),
                "sanctions_imposed": match.get("sanctions_imposed"),
                "date_designated": match.get("date_designated"),
            }
        )
    elif source == "swiss-seco":
        details.update(
            {
                "list_date": data.get("list_date"),
                "list_type": data.get("list_type"),
                "ssid": match.get("ssid"),
                "subject_type": match.get("subject_type"),
                "program_key": match.get("program_key"),
                "program_origin": match.get("program_origin"),
                "sanctions_set_ids": match.get("sanctions_set_ids"),
            }
        )
    elif source == "eu-consolidated-sanctions":
        details.update(
            {
                "generation_date": data.get("generation_date"),
                "global_file_id": data.get("global_file_id"),
                "logical_id": match.get("logical_id"),
                "eu_reference_number": match.get("eu_reference_number"),
                "subject_type": match.get("subject_type"),
                "programme": match.get("programme"),
                "regulation_number_title": match.get("regulation_number_title"),
            }
        )
    return details


def _extract_jurisdiction(source: str) -> str | None:
    if source == "uk-sanctions-list":
        return "GB"
    if source == "swiss-seco":
        return "CH"
    if source == "eu-consolidated-sanctions":
        return "EU"
    return None


class SanctionsEnforcementWatchlistsAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="sanctions_enforcement_watchlists",
        license="Composite adapter; sub-sources are official government sanctions list publications (UK FCDO, Swiss SECO, EU Financial Sanctions Files)",
        input_types=[SeedType.NAME, SeedType.COMPANY_NAME, SeedType.PERSON_NAME],
        output_types=[EntityType.SANCTION],
        legal_notes=[
            "Composite adapter covering the three sanctions-list sub-sources of the sanctions_enforcement_watchlists batch: uk-sanctions-list (UK Sanctions List, FCDO), swiss-seco (Swiss sanctions list, SECO/SESAM) and eu-consolidated-sanctions (EU consolidated financial sanctions list, Financial Sanctions Files).",
            "The batch plan assigns six sub-sources to this batch. Three of them (finra-brokercheck, fed-enforcement, occ-enforcement) are already implemented in government_records_us.py and are deliberately not duplicated here; this overlap is recorded in the manifest note and in docker/sanctions_enforcement_watchlists/RATE_LIMITS.md.",
            "All three sub-sources publish a bulk XML artefact. No JSON search API is claimed for any of them: the runner downloads the published list once per run and filters it locally by name.",
            "A hit is a screening match on normalized name text, not a confirmed identity match. It must be reviewed against the published record before it is relied on.",
            "No API key, account or credential is used. Only the fixed public download token published in the European Commission's own open-data dataset record is sent to the EU endpoint.",
            "Rate limits are not published for any of the three sub-sources; the adapter queries each at most once per run and downloads one full list per sub-source.",
        ],
        rate_limit="One full-list download per sub-source per run; 3 sub-sources total. No documented numeric quota exists for any of them; see docker/sanctions_enforcement_watchlists/RATE_LIMITS.md",
        invocation="HTTPS bulk list downloads via dedicated Docker runner (aletheia/sanctions-watchlists:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/sanctions_enforcement_watchlists",
        network_required=True,
        docker_image="aletheia/sanctions-watchlists:v1",
        output_schema={"finding_type": "SanctionsEnforcementWatchlistsFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[],
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
                findings.append(SanctionsEnforcementWatchlistsFinding(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    record_type=None,
                    entity_name=None,
                    identifier=None,
                    jurisdiction=None,
                    date=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_sanctions_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(SanctionsEnforcementWatchlistsFinding(
                    subject=f"{source_name}:error",
                    source=source_name,
                    record_type=None,
                    entity_name=None,
                    identifier=None,
                    jurisdiction=None,
                    date=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_sanctions_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)
            jurisdiction = _extract_jurisdiction(source_name)

            finding = SanctionsEnforcementWatchlistsFinding(
                subject=subject,
                source=source_name,
                record_type=record_type,
                entity_name=input_value,
                identifier=subject,
                jurisdiction=jurisdiction,
                date=timestamp[:10] if timestamp else None,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_sanctions_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
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
    if name == "SanctionsEnforcementWatchlistsAdapter":
        return SanctionsEnforcementWatchlistsAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
