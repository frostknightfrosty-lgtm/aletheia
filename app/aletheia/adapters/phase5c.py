from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
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


def _provenance(adapter: AdapterDescriptor, source_url: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool=adapter.name,
        source_url=source_url,
        confidence=0.90,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=notes,
    )


def _result(request: AdapterRunRequest, adapter: AdapterDescriptor, started: datetime,
            findings: list[Finding], stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
    return AdapterRunResult(
        run_id=request.run_id,
        adapter=adapter,
        status="succeeded" if exit_code == 0 else "partial",
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        exit_code=exit_code,
        findings=findings,
        stderr_tail=stderr[-4000:],
        stdout_tail=stdout[-4000:],
    )


def _email_hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _https_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc:
        return None
    return value


class GravatarAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="gravatar",
        license="Gravatar Public API terms; no client library bundled",
        input_types=[SeedType.EMAIL],
        output_types=[EntityType.SOCIAL_ACCOUNT],
        legal_notes=[
            "Requires an explicit authorization assertion for the email seed. The wrapper sends only the SHA-256 hash of the trimmed, lowercase email to the documented profile endpoint; the email itself is not passed to Docker or the API.",
            "Gravatar profile-page visibility controls do not hide all fields from its public API. The container curates the response before output and the parser re-applies the same allowlist: contact details, wallets, links, galleries, and verified-account data never leave the container, and a result is only a provider-reported profile association, not proof of identity.",
            "The profile API resolves only the primary email address associated with an account. Respect current provider rate limits; an optional API key may be supplied through GRAVATAR_API_KEY.",
        ],
        rate_limit="One profile lookup per run; respect provider quotas and HTTP 429 responses.",
        invocation="HTTPS API via dedicated Docker runner",
        version_pin="Gravatar Profiles API v3",
        upstream="https://docs.gravatar.com/sdk/profiles/",
        network_required=True,
        docker_image="aletheia/gravatar:api-v3",
        output_schema={"profile": "curated public profile fields"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=["GRAVATAR_API_KEY"],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.EMAIL

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        # The image ENTRYPOINT already runs `python /opt/runner.py`; pass arguments only.
        # Keep the raw email out of Docker argv and the adapter invocation audit record.
        return ["hash", _email_hash(request.seed.value)]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str,
              exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode("utf-8")
        findings: list[Finding] = []
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
        expected_hash = _email_hash(request.seed.value)
        if isinstance(payload, dict) and payload.get("hash") == expected_hash:
            attributes: dict[str, object] = {"email_sha256": expected_hash}
            for field in ("display_name", "location", "description", "job_title", "company"):
                value = payload.get(field)
                if isinstance(value, str) and value.strip():
                    attributes[field] = value
            if payload.get("is_organization") is True:
                attributes["is_organization"] = True
            profile_url = _https_url(payload.get("profile_url"))
            avatar_url = _https_url(payload.get("avatar_url"))
            if avatar_url:
                attributes["avatar_url"] = avatar_url
            if profile_url:
                attributes["profile_url"] = profile_url
                source_url = f"https://api.gravatar.com/v3/profiles/{expected_hash}"
                findings.append(Finding(
                    entity_type=EntityType.SOCIAL_ACCOUNT,
                    value=profile_url,
                    attributes=attributes,
                    provenance=_provenance(
                        self.descriptor,
                        source_url,
                        raw,
                        ["Gravatar public profile response for the exact email SHA-256. This is an association signal, not identity confirmation."],
                    ),
                ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)
