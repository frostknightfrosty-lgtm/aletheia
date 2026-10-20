"""Public Mojang Minecraft profile adapter.

The runner makes at most two unauthenticated public requests: a current Java
username lookup and the session profile for the texture property. NameMC is not
used: it has no public API and its terms do not authorize scraping. The adapter
emits the current handle/UUID and public skin/cape metadata only.
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

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
UUID_RE = re.compile(r"^[0-9a-f]{32}$")
DASHED_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


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


class MinecraftAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="minecraft",
        license=(
            "Public Mojang Minecraft profile API; no third-party code. NameMC "
            "is not used because it has no public API and does not authorize "
            "scraping."
        ),
        input_types=[SeedType.USERNAME],
        output_types=[EntityType.SOCIAL_ACCOUNT, EntityType.TECHNICAL_FINDING],
        legal_notes=[
            "At most two unauthenticated public GETs per run: the current Java "
            "username lookup on api.mojang.com and the public session profile "
            "on sessionserver.mojang.com. No credentials, token, retry, "
            "pagination, or proxy rotation; 30-second timeout and 1 MB cap.",
            "Only the current public handle, UUID, session name, and public "
            "skin/cape URLs plus skin model are emitted. Texture signatures, "
            "the raw texture property, profile actions, and all images are "
            "discarded. The removed name-history endpoint is not called.",
            "A Minecraft handle is a same-handle lead, not identity proof. "
            "Usernames can be changed and transferred; Mojang exposes only the "
            "current name. NameMC history is deliberately out of scope. No live "
            "target is on file; verification is fixture-based. See "
            "docker/minecraft/RATE_LIMITS.md.",
        ],
        rate_limit=(
            "Two unauthenticated public GETs per run; 30-second timeout; 1 MB "
            "cap; no retries or pagination. The response header "
            "x-minecraft-rate-limit-result is recorded; a 204 means no such "
            "profile, a 429/403 is a bounded error. See "
            "docker/minecraft/RATE_LIMITS.md"
        ),
        invocation="Docker / CLI",
        version_pin="1.0 (Mojang public profile API; reviewed 2026-10-20)",
        upstream="https://api.mojang.com",
        network_required=True,
        docker_image="aletheia/minecraft:v1",
        output_schema={"finding_type": "Finding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.USERNAME

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        username = request.seed.value.strip()
        if not USERNAME_RE.fullmatch(username):
            raise ValueError("invalid Minecraft username")
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
        username = _text(payload.get("username"), 16) or request.seed.value.strip()
        errors = [
            value for value in (
                _text(item, 300) for item in (
                    payload.get("errors") if isinstance(payload.get("errors"), list) else []
                )[:5]
            ) if value
        ]
        compact = _text(payload.get("uuid"), 32)
        dashed = _text(payload.get("uuid_dashed"), 36)
        if compact and not UUID_RE.fullmatch(compact):
            compact = None
        if dashed and not DASHED_RE.fullmatch(dashed):
            dashed = None
        if compact and not dashed:
            dashed = (
                f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-"
                f"{compact[16:20]}-{compact[20:32]}"
            )

        findings: list[Finding] = [Finding(
            entity_type=EntityType.SOCIAL_ACCOUNT,
            value=f"{self.descriptor.name}:run:{status}",
            attributes={
                "source": self.descriptor.name,
                "status": status,
                "username": username,
                "uuid_dashed": dashed,
                "rate_limit_result": _text(payload.get("rate_limit_result"), 64),
                "errors": errors,
            },
            provenance=_prov(
                self.descriptor, 0.2, raw,
                ["Mojang public profile lookup; a handle is not identity proof."],
            ),
        )]

        if status in {"ok", "partial"} and compact and dashed:
            findings.append(Finding(
                entity_type=EntityType.TECHNICAL_FINDING,
                value=f"{self.descriptor.name}:uuid:{dashed}",
                attributes={
                    "source": self.descriptor.name,
                    "kind": "minecraft_uuid",
                    "username": username,
                    "uuid": compact,
                    "uuid_dashed": dashed,
                },
                provenance=_prov(
                    self.descriptor, 0.7, raw,
                    ["Mojang account UUID; stable account identifier, not a person."],
                ),
            ))
            findings.append(Finding(
                entity_type=EntityType.SOCIAL_ACCOUNT,
                value=f"{self.descriptor.name}:profile:{username}",
                attributes={
                    "source": self.descriptor.name,
                    "platform": "minecraft",
                    "username": username,
                    "session_name": _text(payload.get("session_name"), 16),
                    "uuid_dashed": dashed,
                    "skin_url": _text(payload.get("skin_url"), 500),
                    "cape_url": _text(payload.get("cape_url"), 500),
                    "skin_model": _text(payload.get("skin_model"), 16),
                    "rate_limit_result": _text(payload.get("rate_limit_result"), 64),
                    "name_history": "not collected",
                },
                provenance=_prov(
                    self.descriptor, 0.6, raw,
                    [
                        "Current Mojang profile; no NameMC history was fetched. "
                        "Same-handle candidate, not identity proof."
                    ],
                ),
            ))
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status=(
                "succeeded"
                if exit_code == 0 and status in {"ok", "not_found"}
                else "partial"
            ),
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )
