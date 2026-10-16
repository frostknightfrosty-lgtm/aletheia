from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
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


SUPPORTED_SUB_SOURCES = ("masto", "octosuite")

UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "owasp-socialosintlm": (
        "The current official OWASP project is Social OSINT Agent, an autonomous multi-platform "
        "agent that uses an OpenAI-compatible LLM API. Its external platform integrations and LLM "
        "credentials are not available in this keyless composite, so it is not invoked. The upstream "
        "candidate name SocialOSINTLM does not exactly match the current OWASP project name. See "
        "https://owasp.org/www-project-social-osint-agent/ and "
        "https://owasp.github.io/www-project-social-osint-agent/."
    ),
    "scrawler": (
        "The upstream project states it has a GUI and no CLI; its documented Reddit and META "
        "profile retrieval depends on user cookies/OAuth. It has no bounded, unattended, keyless "
        "username-query interface for this container, so it is not invoked. See "
        "https://github.com/AAndyProgram/SCrawler/blob/main/FAQ.md."
    ),
}

_SOURCE_DOCS = {
    "masto": "https://docs.joinmastodon.org/methods/search/",
    "octosuite": "https://docs.github.com/en/rest/users/users#get-a-user",
}

_GITHUB_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")


def _query_username(value: str, *, source: str) -> str | None:
    normalized = value.strip()
    if normalized.startswith("@"): 
        normalized = normalized[1:]

    if source == "masto" and "@" in normalized:
        pieces = normalized.split("@")
        if len(pieces) != 2 or pieces[1].casefold() != "mastodon.social":
            return None
        normalized = pieces[0]
    elif "@" in normalized:
        return None

    if source == "octosuite":
        return normalized if _GITHUB_LOGIN.fullmatch(normalized) else None
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", normalized):
        return None
    return normalized


def _provenance(source: str, values: dict[str, Any], source_url: str) -> Provenance:
    raw = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return Provenance(
        tool="social_username",
        source_url=source_url,
        confidence=0.75,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=[
            f"Public username lookup from {source}; confidence describes the source observation, "
            "not identity or account ownership."
        ],
    )


class SocialUsernameFinding(Finding):
    """Minimal public profile observation associated with a username search."""

    platform: str | None = None
    username: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    source_url: str

    def __init__(
        self,
        *,
        source: str,
        platform: str,
        username: str,
        profile_url: str,
        display_name: str | None = None,
        provenance: Provenance | None = None,
    ) -> None:
        attributes: dict[str, Any] = {
            "source": source,
            "platform": platform,
            "username": username,
            "profile_url": profile_url,
        }
        if display_name:
            attributes["display_name"] = display_name
        if provenance is None:
            provenance = _provenance(source, attributes, profile_url)
        super().__init__(
            entity_type=EntityType.SOCIAL_ACCOUNT,
            value=f"{platform}:{username}",
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
            source_url=profile_url,
        )
        self.platform = platform
        self.username = username
        self.display_name = display_name
        self.profile_url = profile_url


class SocialUsernameAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="social_username",
        license=(
            "Composite adapter using MIT-licensed Masto 2.0.5 API behavior and Octosuite 5.1.0 "
            "public-user lookup semantics; only their documented public endpoints are called."
        ),
        input_types=[SeedType.USERNAME],
        output_types=[EntityType.SOCIAL_ACCOUNT],
        legal_notes=[
            "Masto is restricted to one GET of Mastodon's documented /api/v2/search endpoint on "
            "mastodon.social, with type=accounts, limit=5, and no authenticated resolve or pagination. "
            "The runner emits only exact username matches whose public discoverable field is true; "
            "it does not use Masto's cross-instance list scan or return accounts marked not discoverable.",
            "Octosuite is restricted to its public GitHub user-profile endpoint, one GET per run, "
            "with redirects disabled and a five-second timeout. Only the public username, display name, "
            "and canonical profile URL are emitted; public email, biography, and other fields are discarded.",
            "OWASP SocialOSINTAgent and scrawler are non-querying drops because this image has no "
            "platform/LLM credentials or user cookies and does not use an interactive GUI. See "
            "docker/social_username/RATE_LIMITS.md.",
        ],
        rate_limit=(
            "At most one request to mastodon.social and one request to api.github.com per run; "
            "five-second timeout, no redirects, no retries, and stop on rate-limit errors. "
            "See docker/social_username/RATE_LIMITS.md for vendor quotas and drop decisions."
        ),
        invocation="Bounded public Mastodon Search API and Octosuite public-user lookup via dedicated Docker runner (aletheia/social-username:v1)",
        version_pin="Masto 2.0.5 behavior; Octosuite 5.1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/social_username",
        network_required=True,
        docker_image="aletheia/social-username:v1",
        output_schema={
            "finding_type": "SocialUsernameFinding",
            "fields": ["source", "platform", "username", "display_name", "profile_url"],
        },
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.USERNAME

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        if not self.supports(request.seed.type):
            raise ValueError(f"Unsupported seed type for social_username: {request.seed.type}")
        return ["username", request.seed.value]

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
            expected_username = _query_username(request.seed.value, source=source)
            if expected_username is None:
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                if source == "masto" and record.get("discoverable") is not True:
                    continue
                username = str(record.get("username") or "").strip()
                if username.casefold() != expected_username.casefold():
                    continue
                profile_url = str(record.get("profile_url") or "")
                parsed_url = urlsplit(profile_url)
                if (
                    parsed_url.scheme != "https"
                    or not parsed_url.hostname
                    or parsed_url.username is not None
                    or parsed_url.password is not None
                    or parsed_url.hostname.lower().rstrip(".") == "localhost"
                ):
                    continue
                if source == "octosuite" and parsed_url.hostname.lower().rstrip(".") != "github.com":
                    continue
                if profile_url in seen_urls:
                    continue
                seen_urls.add(profile_url)
                display_name = str(record.get("display_name") or "").strip() or None
                values = {
                    "source": source,
                    "platform": "mastodon" if source == "masto" else "github",
                    "username": username,
                    "profile_url": profile_url,
                }
                if display_name:
                    values["display_name"] = display_name
                findings.append(
                    SocialUsernameFinding(
                        source=source,
                        platform=values["platform"],
                        username=username,
                        profile_url=profile_url,
                        display_name=display_name,
                        provenance=_provenance(source, values, profile_url),
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
