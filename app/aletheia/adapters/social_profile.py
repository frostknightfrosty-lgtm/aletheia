from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


SUPPORTED_SUB_SOURCES = ("crosslinked", "slinky")

UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "tiktok-hashtag-analysis": (
        "The upstream collector uses TikTokApi with Playwright and automatically retries a fetch "
        "in headed-browser mode after errors. TikTokApi's session code enables browser stealth and "
        "simulates pointer movement to avoid bot detection. The documented collector does not expose "
        "a bounded, stable public API contract that can be used without that anti-detection path; "
        "this adapter does not invoke it. See https://github.com/bellingcat/tiktok-hashtag-analysis/blob/main/tiktok_hashtag_analysis/base.py "
        "and https://github.com/davidteather/TikTok-Api/blob/main/TikTokApi/tiktok.py."
    ),
    "zehef": (
        "Zehef is email-input oriented, not a social-profile lookup. Its code combines account "
        "existence checks with breach/stealer-data queries, including an Instagram account-creation "
        "attempt endpoint and Hudson Rock credential fields. Those functions do not fit this profile "
        "batch's input or output scope and are not called. See "
        "https://github.com/N0rz3/Zehef/blob/master/modules/accounts/instagram.py, "
        "https://github.com/N0rz3/Zehef/blob/master/modules/breaches/hudsonrock.py, and "
        "https://github.com/N0rz3/Zehef/blob/master/README.md."
    ),
}

_SOURCE_DOCS = {
    "crosslinked": "https://github.com/m8sec/CrossLinked",
    "slinky": "https://github.com/FurqanSoftware/slinky",
}


def _provenance(
    source: str,
    evidence: dict[str, Any],
    source_url: str,
) -> Provenance:
    raw = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    confidence = 0.65 if source == "crosslinked" else 0.85
    notes = [f"Parsed using {source}; confidence describes the public observation or URL structure, not account ownership."]
    return Provenance(
        tool="social_profile",
        source_url=source_url,
        confidence=confidence,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


class SocialProfileFinding(Finding):
    """Read-only social-profile fields permitted by the project policy."""

    name: str | None = None
    username: str | None = None
    email: str | None = None
    company: str | None = None
    source_url: str

    def __init__(
        self,
        *,
        source: str,
        source_url: str,
        name: str | None = None,
        username: str | None = None,
        email: str | None = None,
        company: str | None = None,
        provenance: Provenance | None = None,
    ) -> None:
        allowed = {
            "name": name,
            "username": username,
            "email": email,
            "company": company,
            "source_url": source_url,
        }
        attributes = {key: value for key, value in allowed.items() if value is not None}
        if provenance is None:
            provenance = _provenance(source, attributes, source_url)
        value = name or username or source_url
        super().__init__(
            entity_type=EntityType.SOCIAL_ACCOUNT,
            value=value,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
            source_url=source_url,
        )
        self.name = name
        self.username = username
        self.email = email
        self.company = company
        self.source_url = source_url


class SocialProfileAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="social_profile",
        license=(
            "Composite adapter: CrossLinked (GPL-3.0) is installed in its isolated image; "
            "Slinky (BSD-3-Clause) is pinned to a source commit and used as an offline URL parser."
        ),
        input_types=[SeedType.COMPANY_NAME, SeedType.URL],
        output_types=[EntityType.SOCIAL_ACCOUNT],
        legal_notes=[
            "CrossLinked performs at most one HTTPS search-page request to each of Google and Bing per company-name run, with certificate verification enabled, no redirects, no retries, no proxy rotation, and a five-second request timeout. It does not contact LinkedIn directly. Search-engine challenges are surfaced as source errors and are never retried or bypassed.",
            "Only name, username (the public profile URL slug), company, and source_url may be emitted. Job titles, generated email patterns, raw search snippets, and authentication endpoints are not returned.",
            "Slinky parses an HTTPS social-profile URL locally and makes no network request. Its confidence describes the URL shape only, not the account owner's identity.",
            "The TikTok and Zehef candidates are non-querying drops with source-specific reasons in docker/social_profile/RATE_LIMITS.md.",
        ],
        rate_limit=(
            "CrossLinked is capped at one request to Google and one to Bing per run (two total), "
            "five-second timeout each, no redirect following or retry. Slinky performs no network request. "
            "Neither provider publishes a numeric quota; see docker/social_profile/RATE_LIMITS.md."
        ),
        invocation="Bounded public search HTML parser and offline Slinky URL parser via a dedicated Docker image (aletheia/social-profile:v1)",
        version_pin="CrossLinked 0.3.0; Slinky e74a138b6bf7264c788871b2e0825455046d09ef",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/social_profile",
        network_required=True,
        docker_image="aletheia/social-profile:v1",
        output_schema={
            "finding_type": "SocialProfileFinding",
            "fields": ["name", "username", "email", "company", "source_url"],
        },
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.COMPANY_NAME, SeedType.URL}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        if not self.supports(request.seed.type):
            raise ValueError(f"Unsupported seed type for social_profile: {request.seed.type}")
        return [request.seed.type.value, request.seed.value]

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
        errors: list[str] = []
        seen_urls: set[str] = set()
        for source_result in payload.get("sources", []):
            if not isinstance(source_result, dict) or source_result.get("skipped"):
                continue
            source = str(source_result.get("source", ""))
            if source_result.get("error"):
                errors.append(f"{source}: {source_result['error']}")
            data = source_result.get("data")
            if not isinstance(data, dict):
                continue
            records = data.get("records", [])
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                source_url = str(record.get("source_url") or "")
                parsed_url = urlsplit(source_url)
                if parsed_url.scheme != "https" or not parsed_url.hostname:
                    continue
                hostname = parsed_url.hostname.lower().rstrip(".")
                if source == "crosslinked" and not (
                    (hostname == "linkedin.com" or hostname.endswith(".linkedin.com"))
                    and parsed_url.path.lower().startswith("/in/")
                ):
                    continue
                if source_url in seen_urls:
                    continue
                fields = {
                    key: str(record[key]).strip()
                    for key in ("name", "username", "email", "company")
                    if record.get(key) is not None and str(record[key]).strip()
                }
                if not (fields.get("name") or fields.get("username")):
                    continue
                seen_urls.add(source_url)
                provenance = _provenance(source, fields | {"source_url": source_url}, source_url)
                findings.append(
                    SocialProfileFinding(
                        source=source,
                        source_url=source_url,
                        name=fields.get("name"),
                        username=fields.get("username"),
                        email=fields.get("email"),
                        company=fields.get("company"),
                        provenance=provenance,
                    )
                )

        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="partial" if errors else "succeeded",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=1 if errors else 0,
            findings=findings,
            stderr_tail="\n".join(errors)[-4000:],
            stdout_tail=stdout[-4000:],
        )
