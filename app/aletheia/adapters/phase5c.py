from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

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


def _normalize_domain(value: str) -> str | None:
    """Normalize a domain seed or URL to one ASCII DNS name."""
    value = value.strip()
    if not value:
        return None
    candidate = value if "://" in value else f"//{value}"
    try:
        parts = urlsplit(candidate)
        if parts.scheme and parts.scheme.lower() not in {"http", "https"}:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        hostname = parts.hostname
    except ValueError:
        return None
    if not hostname:
        return None
    try:
        domain = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    labels = domain.split(".")
    if len(domain) > 253 or len(labels) < 2:
        return None
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(char.isascii() and (char.isalnum() or char == "-") for char in label)
        for label in labels
    ):
        return None
    return domain


def _normalize_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except (ValueError, TypeError):
        return None


def _rdap_provenance(adapter: AdapterDescriptor, source_url: str, raw: bytes,
                     notes: list[str]) -> Provenance:
    return Provenance(
        tool=adapter.name,
        source_url=source_url,
        confidence=0.85,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=notes,
    )


def _rdap_url_matches(url: str, object_type: str, normalized_seed: str) -> bool:
    try:
        parts = urlsplit(url)
        expected = f"/{object_type}/{quote(normalized_seed, safe=':')}"
        return parts.scheme == "https" and bool(parts.netloc) and parts.path.rstrip("/").endswith(expected)
    except (TypeError, ValueError):
        return False


def _rdap_domain_matches(record: dict[str, object], domain: str) -> bool:
    names = [record[field] for field in ("ldhName", "unicodeName") if isinstance(record.get(field), str)]
    normalized_names = [_normalize_domain(str(value)) for value in names]
    return bool(normalized_names) and all(value == domain for value in normalized_names)


def _rdap_ip_matches(record: dict[str, object], address: str) -> bool:
    expected = _normalize_ip(address)
    start = _normalize_ip(str(record.get("startAddress", "")))
    end = _normalize_ip(str(record.get("endAddress", "")))
    if expected is None or start is None or end is None:
        return False
    target_ip, start_ip, end_ip = map(ipaddress.ip_address, (expected, start, end))
    return target_ip.version == start_ip.version == end_ip.version and int(start_ip) <= int(target_ip) <= int(end_ip)


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


class RdapAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="rdap",
        license="IETF RFC 9082 / RFC 9224 standards; IANA bootstrap registry",
        input_types=[SeedType.DOMAIN, SeedType.IP],
        output_types=[EntityType.DOMAIN, EntityType.IP],
        legal_notes=[
            "Uses IANA RDAP bootstrap data for one exact HTTPS domain or IP lookup matching the supplied seed.",
            "Contact entities, email and postal addresses, remarks, and unreviewed response fields are excluded from output.",
            "Registration data may be incomplete or privacy-protected; it describes registry data and does not establish domain control or registrant identity.",
        ],
        rate_limit="One IANA bootstrap request and one exact registry lookup per run; respect registry responses and limits.",
        invocation="IANA RDAP bootstrap plus exact HTTPS lookup via dedicated Docker runner",
        version_pin="RFC 9082 / RFC 9224",
        upstream="https://www.iana.org/assignments/rdap-dns",
        network_required=True,
        docker_image="aletheia/rdap:rfc9082",
        output_schema={"record": "curated domain or IP registration data"},
        health_check="--health",
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.DOMAIN, SeedType.IP}

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        # The image ENTRYPOINT supplies Python and runner.py; pass arguments only.
        if request.seed.type == SeedType.DOMAIN:
            return ["domain", _normalize_domain(request.seed.value) or request.seed.value]
        return ["ip", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str,
              exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode("utf-8")
        findings: list[Finding] = []
        diagnostic = stderr
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None

        if exit_code == 0 and isinstance(payload, dict) and isinstance(payload.get("record"), dict):
            record = payload["record"]
            if request.seed.type == SeedType.DOMAIN:
                normalized = _normalize_domain(request.seed.value)
                matches = bool(normalized and _rdap_domain_matches(record, normalized))
                url_matches = bool(normalized and isinstance(payload.get("query_url"), str)
                                   and _rdap_url_matches(payload["query_url"], "domain", normalized))
                if matches and url_matches:
                    attributes: dict[str, object] = {}
                    for field in ("handle", "ldhName", "unicodeName"):
                        value = record.get(field)
                        if isinstance(value, str) and value.strip():
                            attributes[field] = value
                    statuses = record.get("status")
                    if isinstance(statuses, list):
                        attributes["status"] = [item for item in statuses if isinstance(item, str)]
                    events = record.get("events")
                    if isinstance(events, list):
                        attributes["events"] = [
                            {key: event[key] for key in ("eventAction", "eventDate")
                             if isinstance(event.get(key), str)}
                            for event in events if isinstance(event, dict)
                        ]
                    nameservers = record.get("nameservers")
                    if isinstance(nameservers, list):
                        attributes["nameservers"] = [
                            item["ldhName"] for item in nameservers
                            if isinstance(item, dict) and isinstance(item.get("ldhName"), str)
                        ]
                    secure_dns = record.get("secureDNS")
                    if isinstance(secure_dns, dict) and isinstance(secure_dns.get("delegationSigned"), bool):
                        attributes["dnssec_delegation_signed"] = secure_dns["delegationSigned"]
                    findings.append(Finding(
                        entity_type=EntityType.DOMAIN,
                        value=normalized,
                        attributes=attributes,
                        provenance=_rdap_provenance(
                            self.descriptor,
                            payload["query_url"],
                            raw,
                            ["Registry-data confidence only (0.85); this record does not establish domain control or registrant identity. Privacy-proxy/contact data is excluded."],
                        ),
                        source_kind="seed",
                    ))
                elif not (matches and url_matches):
                    diagnostic = (diagnostic + "\n" if diagnostic else "") + "RDAP parser rejected response: domain record or query URL did not match the normalized seed."
            elif request.seed.type == SeedType.IP:
                normalized = _normalize_ip(request.seed.value)
                matches = bool(normalized and _rdap_ip_matches(record, normalized))
                url_matches = bool(normalized and isinstance(payload.get("query_url"), str)
                                   and _rdap_url_matches(payload["query_url"], "ip", normalized))
                if matches and url_matches:
                    attributes = {}
                    for field in ("handle", "type", "startAddress", "endAddress", "ipVersion",
                                  "country", "parentHandle"):
                        value = record.get(field)
                        if isinstance(value, str) and value.strip():
                            attributes[field] = value
                    network_name = record.get("name")
                    if isinstance(network_name, str) and network_name.strip():
                        attributes["network_name"] = network_name
                    statuses = record.get("status")
                    if isinstance(statuses, list):
                        attributes["status"] = [item for item in statuses if isinstance(item, str)]
                    findings.append(Finding(
                        entity_type=EntityType.IP,
                        value=normalized,
                        attributes=attributes,
                        provenance=_rdap_provenance(
                            self.descriptor,
                            payload["query_url"],
                            raw,
                            ["Registry-data confidence only (0.85); the network allocation name is not proof of control or identity. Contact data is excluded."],
                        ),
                        source_kind="seed",
                    ))
                else:
                    diagnostic = (diagnostic + "\n" if diagnostic else "") + "RDAP parser rejected response: IP range or query URL did not match the normalized seed."

        return _result(request, self.descriptor, started, findings, stdout, diagnostic, exit_code)
