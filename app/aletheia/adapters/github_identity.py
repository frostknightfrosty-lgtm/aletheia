"""Public GitHub identity-expansion adapter.

The runner (``docker/github_identity/run_github_identity.py``) makes six
unauthenticated public requests: profile, latest public repositories, gists,
public events, the API public-key list, and the public ``.keys`` endpoint. This
parser emits account-scoped findings only; profile email is never carried and
SSH keys are reduced to fingerprints.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
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

USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _list(value: Any, limit: int = 10) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _prov(adapter: AdapterDescriptor, confidence: float, raw: bytes,
          notes: list[str]) -> Provenance:
    return Provenance(
        tool=adapter.name,
        source_url=adapter.upstream,
        observed_at=datetime.now(timezone.utc),
        confidence=confidence,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=notes,
    )


class GithubIdentityAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="github_identity",
        license=(
            "Public GitHub data, used through the documented REST API under "
            "GitHub's Terms of Service and API Terms; no third-party code."
        ),
        input_types=[SeedType.USERNAME],
        output_types=[EntityType.SOCIAL_ACCOUNT, EntityType.TECHNICAL_FINDING],
        legal_notes=[
            "Six unauthenticated public GitHub requests per run: profile, latest "
            "public repositories, gists, public events, the API public-key list, "
            "and https://github.com/<user>.keys. The unauthenticated REST limit "
            "is 60 requests/hour per source IP; the adapter never retries, "
            "paginates, or uses a token.",
            "Only public account-scoped metadata is emitted. The profile email "
            "field is deliberately dropped; repositories, gists and events are "
            "bounded; SSH keys are reduced to their OpenSSH SHA-256 fingerprint "
            "and key type, never stored as key material. Event payloads, avatars "
            "and follower lists are not fetched.",
            "A GitHub handle is a same-handle lead, not identity proof: usernames "
            "are user-chosen, can be renamed or transferred, and public keys may "
            "be shared or stale. No live target is on file; verification is "
            "fixture-based. See docker/github_identity/RATE_LIMITS.md.",
        ],
        rate_limit=(
            "Six unauthenticated public GitHub requests per run (max 5 repos, 5 "
            "gists, 5 events, 10 SSH fingerprints); 30-second timeout per "
            "request; no retries, pagination, token, or proxy rotation. "
            "Unauthenticated REST quota is 60 requests/hour per source IP. See "
            "docker/github_identity/RATE_LIMITS.md"
        ),
        invocation="Docker / CLI",
        version_pin="1.0 (GitHub REST API 2022-11-28; reviewed 2026-10-20)",
        upstream="https://docs.github.com/en/rest",
        network_required=True,
        docker_image="aletheia/github-identity:v1",
        output_schema={"finding_type": "Finding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.USERNAME

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        username = request.seed.value.strip()
        if not USERNAME_RE.fullmatch(username):
            raise ValueError("invalid GitHub username")
        (workspace / "username.txt").write_text(username + "\n", encoding="utf-8")
        return ["/work/username.txt"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str,
              stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode("utf-8", "replace")
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        status = _text(payload.get("status"), 32) or ("ok" if exit_code == 0 else "error")
        username = _text(payload.get("username"), 64) or request.seed.value.strip()
        errors = [
            value for value in (
                _text(item, 300) for item in _list(payload.get("errors"), 10)
            ) if value
        ]
        profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else None
        repos = _list(payload.get("repos"), 5)
        gists = _list(payload.get("gists"), 5)
        events = _list(payload.get("events"), 5)
        keys = _list(payload.get("ssh_keys"), 10)
        rate = _dict(payload.get("rate_limit"))

        findings: list[Finding] = [Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT,
            value=f"{self.descriptor.name}:run:{status}",
            attributes={
                "source": self.descriptor.name,
                "status": status,
                "username": username,
                "profile_present": profile is not None,
                "repo_count": len(repos),
                "gist_count": len(gists),
                "event_count": len(events),
                "ssh_key_count": len(keys),
                "rate_limit": rate,
                "errors": errors,
            },
            provenance=_prov(
                self.descriptor, 0.2, raw,
                ["Public GitHub endpoint expansion; handle matches are leads, not identity proof."],
            ),
        )]

        if profile is not None:
            login = _text(profile.get("login"), 64) or username
            findings.append(Finding(
                entity_type=EntityType.SOCIAL_ACCOUNT,
                value=f"{self.descriptor.name}:profile:{login}",
                attributes={
                    "source": self.descriptor.name,
                    "platform": "github",
                    "login": login,
                    "name": _text(profile.get("name"), 200),
                    "company": _text(profile.get("company"), 200),
                    "blog": _text(profile.get("blog"), 300),
                    "location": _text(profile.get("location"), 200),
                    "bio": _text(profile.get("bio"), 500),
                    "twitter_username": _text(profile.get("twitter_username"), 120),
                    "public_repos": _number(profile.get("public_repos")),
                    "public_gists": _number(profile.get("public_gists")),
                    "followers": _number(profile.get("followers")),
                    "following": _number(profile.get("following")),
                    "created_at": _text(profile.get("created_at"), 64),
                    "updated_at": _text(profile.get("updated_at"), 64),
                    "html_url": _text(profile.get("html_url"), 300),
                    "rate_limit": rate,
                },
                provenance=_prov(
                    self.descriptor, 0.6, raw,
                    ["GitHub public profile; same-handle candidate, not a verified identity."],
                ),
            ))

        if status in {"ok", "partial"} and profile is not None:
            for item in repos:
                if not isinstance(item, dict):
                    continue
                name = _text(item.get("name"), 200)
                if not name:
                    continue
                findings.append(Finding(
                    entity_type=EntityType.TECHNICAL_FINDING,
                    value=f"{self.descriptor.name}:repo:{username}/{name}",
                    attributes={
                        "source": self.descriptor.name,
                        "kind": "github_repository",
                        "name": name,
                        "html_url": _text(item.get("html_url"), 300),
                        "description": _text(item.get("description"), 500),
                        "language": _text(item.get("language"), 80),
                        "topics": [
                            value for value in (
                                _text(topic, 80) for topic in _list(item.get("topics"), 10)
                            ) if value
                        ],
                        "fork": item.get("fork") if isinstance(item.get("fork"), bool) else None,
                        "archived": item.get("archived") if isinstance(item.get("archived"), bool) else None,
                        "stargazers_count": _number(item.get("stargazers_count")),
                        "created_at": _text(item.get("created_at"), 64),
                        "updated_at": _text(item.get("updated_at"), 64),
                    },
                    provenance=_prov(
                        self.descriptor, 0.5, raw,
                        ["Public repository metadata from the profile's latest repositories."],
                    ),
                ))
            for item in gists:
                if not isinstance(item, dict):
                    continue
                gist_id = _text(item.get("id"), 64)
                if not gist_id:
                    continue
                findings.append(Finding(
                    entity_type=EntityType.TECHNICAL_FINDING,
                    value=f"{self.descriptor.name}:gist:{gist_id}",
                    attributes={
                        "source": self.descriptor.name,
                        "kind": "github_gist",
                        "id": gist_id,
                        "html_url": _text(item.get("html_url"), 300),
                        "description": _text(item.get("description"), 300),
                        "public": item.get("public") if isinstance(item.get("public"), bool) else None,
                        "file_count": _number(item.get("file_count")),
                        "created_at": _text(item.get("created_at"), 64),
                        "updated_at": _text(item.get("updated_at"), 64),
                    },
                    provenance=_prov(
                        self.descriptor, 0.5, raw,
                        ["Public gist metadata; contents and files are not fetched."],
                    ),
                ))
            for item in events:
                if not isinstance(item, dict):
                    continue
                event_id = _text(item.get("id"), 64)
                event_type = _text(item.get("type"), 80)
                if not event_id or not event_type:
                    continue
                findings.append(Finding(
                    entity_type=EntityType.TECHNICAL_FINDING,
                    value=f"{self.descriptor.name}:event:{event_id}",
                    attributes={
                        "source": self.descriptor.name,
                        "kind": "github_event",
                        "id": event_id,
                        "type": event_type,
                        "repo_name": _text(item.get("repo_name"), 200),
                        "created_at": _text(item.get("created_at"), 64),
                    },
                    provenance=_prov(
                        self.descriptor, 0.5, raw,
                        ["Public GitHub event type; event payload is not fetched."],
                    ),
                ))
            for item in keys:
                if not isinstance(item, dict):
                    continue
                fingerprint = _text(item.get("fingerprint"), 100)
                if not fingerprint:
                    continue
                findings.append(Finding(
                    entity_type=EntityType.TECHNICAL_FINDING,
                    value=f"{self.descriptor.name}:ssh:{fingerprint}",
                    attributes={
                        "source": self.descriptor.name,
                        "kind": "github_ssh_key",
                        "fingerprint": fingerprint,
                        "key_type": _text(item.get("key_type"), 32),
                        "key_source": _text(item.get("source"), 16),
                    },
                    provenance=_prov(
                        self.descriptor, 0.6, raw,
                        ["Public SSH key fingerprint; key material is never stored."],
                    ),
                ))
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded" if exit_code == 0 and status == "ok" else "partial",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )
