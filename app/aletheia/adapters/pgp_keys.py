"""OpenPGP Web Key Directory (WKD) adapter.

The runner (``docker/pgp_keys/run_pgp_keys.py``) hashes the email local-part,
tries the WKD advanced method, falls back to direct only on a DNS failure, and
parses the returned OpenPGP packets with the standard library. This parser
emits the primary-key fingerprint, key ID, public metadata, and only the User
IDs that contain the requested email; key material is never emitted.
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

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FINGERPRINT_RE = re.compile(r"^[0-9A-F]{40}$")


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


class PgpKeysAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="pgp_keys",
        license=(
            "OpenPGP Web Key Directory public keys (IETF draft-koch-openpgp-"
            "webkey-service); standard-library parsing only, no third-party code."
        ),
        input_types=[SeedType.EMAIL],
        output_types=[EntityType.TECHNICAL_FINDING],
        legal_notes=[
            "One WKD lookup per email: the advanced method, with a direct-method "
            "GET only when the openpgpkey sub-domain does not resolve (as the "
            "specification requires). No Authorization header, token, retry, "
            "proxy rotation, or DANE lookup; 30-second timeout and 2 MB cap.",
            "Only the primary-key fingerprint, key ID, public algorithm/"
            "timestamps, and User IDs containing the requested email are "
            "emitted. All other User IDs are dropped, and no key material is "
            "stored or imported. The raw response is hashed for provenance.",
            "A published key shows that a domain publishes a key for an email, "
            "not that the key is valid, unrevoked, or belongs to a particular "
            "person. Signature/revocation state is not assessed. No live target "
            "is on file; verification is fixture-based against the WKD "
            "specification's sample key. See docker/pgp_keys/RATE_LIMITS.md.",
        ],
        rate_limit=(
            "One or two public HTTPS GETs per email (advanced method, then "
            "direct only on DNS failure); 30-second timeout; 2 MB cap; no "
            "retries, pagination, token, or proxy rotation. WKD defines no "
            "numeric client quota; the adapter makes one lookup at a time. See "
            "docker/pgp_keys/RATE_LIMITS.md"
        ),
        invocation="Docker / CLI",
        version_pin="1.0 (WKD draft-koch-openpgp-webkey-service-22; reviewed 2026-10-20)",
        upstream="https://datatracker.ietf.org/doc/html/draft-koch-openpgp-webkey-service",
        network_required=True,
        docker_image="aletheia/pgp-keys:v1",
        output_schema={"finding_type": "Finding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.EMAIL

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        email = request.seed.value.strip()
        if len(email) > 254 or not EMAIL_RE.fullmatch(email):
            raise ValueError("invalid email address")
        local, _, domain = email.rpartition("@")
        if not local or len(local) > 64 or not domain or len(domain) > 253:
            raise ValueError("invalid email address")
        (workspace / "email.txt").write_text(email + "\n", encoding="utf-8")
        return ["/work/email.txt"]

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
        email = _text(payload.get("email"), 254) or request.seed.value.strip()
        errors = [
            value for value in (
                _text(item, 300) for item in _list(payload.get("errors"), 5)
            ) if value
        ]
        keys = _list(payload.get("keys"), 5)
        method = _text(payload.get("method"), 16)
        url = _text(payload.get("url"), 500)

        findings: list[Finding] = [Finding(
            entity_type=EntityType.TECHNICAL_FINDING,
            value=f"{self.descriptor.name}:run:{status}",
            attributes={
                "source": self.descriptor.name,
                "status": status,
                "email": email,
                "method": method,
                "url": url,
                "http_status": _number(payload.get("http_status")),
                "key_count": len(keys),
                "key_block_sha256": _text(payload.get("key_block_sha256"), 64),
                "key_block_bytes": _number(payload.get("key_block_bytes")),
                "errors": errors,
            },
            provenance=_prov(
                self.descriptor, 0.2, raw,
                ["WKD lookup result; a published key is not proof of identity."],
            ),
        )]

        if status == "ok":
            for item in keys:
                if not isinstance(item, dict):
                    continue
                fingerprint = _text(item.get("fingerprint"), 40)
                if not fingerprint or not FINGERPRINT_RE.fullmatch(fingerprint):
                    continue
                user_ids = [
                    value for value in (
                        _text(uid, 300) for uid in _list(item.get("user_ids"), 5)
                    ) if value and email.casefold() in value.casefold()
                ]
                if not user_ids:
                    continue
                findings.append(Finding(
                    entity_type=EntityType.TECHNICAL_FINDING,
                    value=f"{self.descriptor.name}:{fingerprint}",
                    attributes={
                        "source": self.descriptor.name,
                        "kind": "openpgp_primary_key",
                        "fingerprint": fingerprint,
                        "key_id": _text(item.get("key_id"), 16),
                        "version": _number(item.get("version")),
                        "algorithm": _number(item.get("algorithm")),
                        "algorithm_name": _text(item.get("algorithm_name"), 64),
                        "created_at": _text(item.get("created_at"), 64),
                        "user_ids": user_ids,
                        "other_uid_count": _number(item.get("other_uid_count")),
                        "wkd_method": method,
                        "wkd_url": url,
                        "key_block_sha256": _text(payload.get("key_block_sha256"), 64),
                    },
                    provenance=_prov(
                        self.descriptor, 0.7, raw,
                        [
                            "Domain-published WKD key for the requested email; "
                            "validity and revocation are not assessed."
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
