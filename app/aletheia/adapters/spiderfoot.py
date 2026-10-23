"""SpiderFoot 4.0 batch meta-adapter.

SpiderFoot is a *meta*-adapter: its findings are secondary evidence that
corroborates or enriches the native adapter graph. The adapter never replaces
native observations, and every finding it emits carries
``source_priority="secondary"`` plus the originating SpiderFoot module,
event type, and data-source website.

The Docker runner enables a curated 14-module catalogue (see
``docker/spiderfoot/MODULES.md``). It emits an envelope containing the
SpiderFoot JSON event array, the runnable module list, and explicit skip records
for keyed modules whose environment variable is absent. This parser accepts
that envelope or a raw SpiderFoot JSON event array.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

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

SPIDERFOOT_COMMIT = "b9c345de5b085debc7444fc10e0e26e7745df5f2"
SPIDERFOOT_VERSION = "4.0.0"

# Keep this catalogue in sync with docker/spiderfoot/runner.py. It is duplicated
# on purpose: the Docker build context cannot import the application package,
# and the adapter must stay readable without building the image.
MODULE_CATALOG: dict[str, dict[str, Any]] = {
    "sfp_threatcrowd": {"source": "ThreatCrowd", "website": "https://www.threatcrowd.org/", "legal_tier": 1, "legal_label": "public no-auth passive", "requires_key": False, "env": None},
    "sfp_threatminer": {"source": "ThreatMiner", "website": "https://www.threatminer.org/", "legal_tier": 1, "legal_label": "public no-auth passive", "requires_key": False, "env": None},
    "sfp_robtex": {"source": "Robtex", "website": "https://www.robtex.com/", "legal_tier": 1, "legal_label": "public no-auth passive", "requires_key": False, "env": None},
    "sfp_keybase": {"source": "Keybase", "website": "https://keybase.io/", "legal_tier": 1, "legal_label": "public no-auth passive", "requires_key": False, "env": None},
    "sfp_openphish": {"source": "OpenPhish", "website": "https://openphish.com/", "legal_tier": 1, "legal_label": "public no-auth passive", "requires_key": False, "env": None},
    "sfp_phishtank": {"source": "PhishTank", "website": "https://phishtank.com/", "legal_tier": 1, "legal_label": "public no-auth passive", "requires_key": False, "env": None},
    "sfp_threatfox": {"source": "ThreatFox (abuse.ch)", "website": "https://threatfox.abuse.ch/", "legal_tier": 2, "legal_label": "public abuse feed, no auth", "requires_key": False, "env": None},
    "sfp_abusech": {"source": "abuse.ch", "website": "https://abuse.ch/", "legal_tier": 2, "legal_label": "public abuse feed, no auth", "requires_key": False, "env": None},
    "sfp_emailrep": {"source": "EmailRep", "website": "https://emailrep.io/", "legal_tier": 3, "legal_label": "free authenticated, rate limited", "requires_key": True, "env": "EMAILREP_API_KEY"},
    "sfp_hunter": {"source": "Hunter", "website": "https://hunter.io/", "legal_tier": 3, "legal_label": "free authenticated, rate limited", "requires_key": True, "env": "HUNTER_API_KEY"},
    "sfp_pulsedive": {"source": "Pulsedive", "website": "https://pulsedive.com/", "legal_tier": 3, "legal_label": "free authenticated, rate limited", "requires_key": True, "env": "PULSEDIVE_API_KEY"},
    "sfp_intelx": {"source": "Intelligence X", "website": "https://intelx.io/", "legal_tier": 4, "legal_label": "commercial or leak-index source", "requires_key": True, "env": "INTELX_API_KEY"},
    "sfp_c99": {"source": "C99", "website": "https://c99.nl/", "legal_tier": 4, "legal_label": "commercial or leak-index source", "requires_key": True, "env": "C99_API_KEY"},
    "sfp_haveibeenpwned": {"source": "Have I Been Pwned", "website": "https://haveibeenpwned.com/", "legal_tier": 4, "legal_label": "commercial or leak-index source", "requires_key": True, "env": "HIBP_API_KEY"},
}

_UNKNOWN_MODULE = {
    "source": "SpiderFoot module",
    "website": "https://github.com/smicallef/spiderfoot",
    "legal_tier": 0,
    "legal_label": "unlisted module",
    "requires_key": False,
    "env": None,
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}")
_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+", re.IGNORECASE)
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_TECHNICAL_PREFIXES = ("MALICIOUS_", "BLACKLISTED_")

_PLATFORM_HOSTS = {
    "twitter.com": "twitter",
    "x.com": "twitter",
    "github.com": "github",
    "gitlab.com": "gitlab",
    "keybase.io": "keybase",
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "reddit.com": "reddit",
    "t.me": "telegram",
    "telegram.me": "telegram",
    "youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "medium.com": "medium",
    "mastodon.social": "mastodon",
    "threads.net": "threads",
}

_URL_ROUTE_PREFIXES = frozenset({"in", "u", "user", "users", "profile", "people", "company", "channel", "c"})
_NON_DATA_EVENTS = frozenset({"RAW_RIR_DATA", "PGP_KEY", "ROOT"})


def _text(value: Any, limit: int = 8192) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()[:limit]


def _event_time(value: Any) -> datetime:
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            stamp = datetime.fromisoformat(text)
        except ValueError:
            stamp = None
        if stamp is not None:
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _module_meta(module: str) -> dict[str, Any]:
    return MODULE_CATALOG.get(module, {**_UNKNOWN_MODULE, "name": module})


def _raw_hash(event: dict[str, Any]) -> str:
    raw = json.dumps(event, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()


def _provenance(event: dict[str, Any], module_meta: dict[str, Any],
                request: AdapterRunRequest, notes: Iterable[str]) -> Provenance:
    return Provenance(
        tool="spiderfoot",
        source_url=str(module_meta.get("website") or "https://github.com/smicallef/spiderfoot"),
        observed_at=_event_time(event.get("generated")),
        confidence=0.60,
        raw_evidence_sha256=_raw_hash(event),
        adapter_version=f"{SPIDERFOOT_VERSION} ({SPIDERFOOT_COMMIT[:12]})",
        seed_index=request.seed_index,
        notes=[
            f"SpiderFoot module {event.get('module', 'unknown')}",
            f"event type {event.get('type', 'unknown')}",
            f"legal tier {module_meta.get('legal_tier')}: {module_meta.get('legal_label')}",
            *notes,
        ],
    )


def _base_attributes(event: dict[str, Any], module_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "spiderfoot",
        "data_source": module_meta.get("source"),
        "spiderfoot_module": _text(event.get("module"), 128),
        "spiderfoot_event_type": _text(event.get("type"), 128),
        "spiderfoot_source": _text(event.get("source"), 1024),
        "legal_tier": module_meta.get("legal_tier"),
        "legal_tier_label": module_meta.get("legal_label"),
        "event_generated": _text(event.get("generated"), 64),
        "source_priority": "secondary",
    }


def _finding(request: AdapterRunRequest, event: dict[str, Any], module_meta: dict[str, Any],
             entity_type: EntityType, value: str, attributes: dict[str, Any],
             notes: Iterable[str] = ()) -> Finding:
    return Finding(
        entity_type=entity_type,
        value=value,
        attributes=attributes,
        provenance=_provenance(event, module_meta, request, notes),
        source_kind="derived",
        source_priority="secondary",
    )


def _first_email(value: str) -> str | None:
    match = _EMAIL_RE.search(value)
    return match.group(0).lower() if match else None


def _first_url(value: str) -> str | None:
    match = _URL_RE.search(value)
    return match.group(0).rstrip(".,;") if match else None


def _platform_for_host(host: str) -> str | None:
    host = host.lower().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    for candidate, platform in _PLATFORM_HOSTS.items():
        if host == candidate or host.endswith("." + candidate):
            return platform
    return None


def _account_from_url(url: str) -> tuple[str | None, str | None]:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None, None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None, None
    platform = _platform_for_host(parsed.netloc)
    segments = [unquote(part) for part in parsed.path.split("/") if part]
    if segments and segments[0].lower() in _URL_ROUTE_PREFIXES:
        segments = segments[1:]
    username = segments[0].lstrip("@") if segments else None
    if username and not _USERNAME_RE.match(username):
        username = None
    return username, platform


def _account_from_event(value: str) -> tuple[str | None, str | None, str | None]:
    url = _first_url(value)
    if url:
        username, platform = _account_from_url(url)
        return url, username, platform
    # Some feeds emit "twitter: alice" rather than a URL.
    prefix, _, remainder = value.partition(":")
    username = remainder.strip().lstrip("@") if remainder else value.strip().lstrip("@")
    if username and _USERNAME_RE.match(username):
        return None, username, prefix.strip().lower() or None
    return None, None, None


def _malicious_mapping(event_type: str) -> EntityType | None:
    if "EMAIL" in event_type:
        return EntityType.EMAIL
    if "IP" in event_type:
        return EntityType.IP
    if "URL" in event_type:
        return EntityType.URL
    if "INTERNET_NAME" in event_type or "DOMAIN" in event_type or "CO_HOSTED" in event_type:
        return EntityType.HOST
    return None


def _map_event(event: dict[str, Any]) -> list[tuple[EntityType, str, dict[str, Any], list[str]]]:
    """Map one SpiderFoot event to normalized Aletheia observations."""
    event_type = _text(event.get("type"), 128).upper()
    data = _text(event.get("data"))
    if not event_type or not data or event_type in _NON_DATA_EVENTS:
        return []

    module = _text(event.get("module"), 128)
    module_meta = _module_meta(module)
    attrs = _base_attributes(event, module_meta)
    out: list[tuple[EntityType, str, dict[str, Any], list[str]]] = []

    def add(entity_type: EntityType, value: str, extra: dict[str, Any] | None = None,
            notes: Iterable[str] = ()) -> None:
        value = value.strip()
        if not value:
            return
        merged = {**attrs, **(extra or {})}
        out.append((entity_type, value, merged, list(notes)))

    if event_type == "DOMAIN_NAME":
        add(EntityType.DOMAIN, data.lower().rstrip("."), {"record_type": "domain"})
    elif event_type in {
        "INTERNET_NAME", "INTERNET_NAME_UNRESOLVED", "AFFILIATE_INTERNET_NAME",
        "CO_HOSTED_SITE", "SIMILAR_DOMAIN", "MALICIOUS_INTERNET_NAME",
        "MALICIOUS_AFFILIATE_INTERNET_NAME", "BLACKLISTED_INTERNET_NAME",
    }:
        add(EntityType.HOST, data.lower().rstrip("."), {
            "record_type": "host",
            "classification": "malicious" if event_type.startswith(_TECHNICAL_PREFIXES) else None,
        })
    elif event_type in {
        "IP_ADDRESS", "IPV6_ADDRESS", "AFFILIATE_IPADDR", "AFFILIATE_IPV6_ADDRESS",
        "MALICIOUS_IPADDR", "MALICIOUS_AFFILIATE_IPADDR", "BLACKLISTED_IPADDR",
    }:
        add(EntityType.IP, data, {
            "record_type": "ip",
            "classification": "malicious" if event_type.startswith(_TECHNICAL_PREFIXES) else None,
        })
    elif event_type in {"EMAILADDR", "EMAILADDR_GENERIC", "EMAILADDR_DELIVERABLE", "EMAILADDR_DISPOSABLE", "MALICIOUS_EMAILADDR"}:
        email = _first_email(data)
        if email:
            add(EntityType.EMAIL, email, {"record_type": "email"})
        else:
            add(EntityType.TECHNICAL_FINDING, f"email-event:{data}", {"record_type": "email", "raw_data": data})
    elif event_type == "EMAILADDR_COMPROMISED":
        email = _first_email(data)
        if email:
            add(EntityType.EMAIL, email, {"record_type": "email", "compromised": True})
        add(EntityType.BREACH_HIT, data, {"record_type": "breach_hit", "breach_kind": "compromised_email"})
    elif event_type in {"PHONE_NUMBER", "PHONE_NUMBER_COMPROMISED"}:
        phone = data.split("[", 1)[0].strip() if "[" in data else data
        add(EntityType.PHONE, phone, {
            "record_type": "phone",
            "compromised": event_type.endswith("_COMPROMISED"),
        })
        if event_type.endswith("_COMPROMISED"):
            add(EntityType.BREACH_HIT, data, {"record_type": "breach_hit", "breach_kind": "compromised_phone"})
    elif event_type in {"ACCOUNT_EXTERNAL_KNOWN", "ACCOUNT_EXTERNAL_OWNED", "SOCIAL_MEDIA"}:
        url, username, platform = _account_from_event(data)
        if username:
            add(EntityType.USERNAME, username, {
                "record_type": "account",
                "platform": platform,
                "account_url": url,
            })
        if url:
            add(EntityType.URL, url, {
                "record_type": "account_url",
                "platform": platform,
            })
        if not username and not url:
            add(EntityType.TECHNICAL_FINDING, f"account-event:{data}", {"record_type": "account", "raw_data": data})
    elif event_type == "LEAKSITE_CONTENT":
        add(EntityType.BREACH_HIT, data, {"record_type": "breach_hit", "breach_kind": "leak_content"})
        # Leak content often embeds the identifier itself. Emitting an email
        # observation lets the Phase 17 cascade route it to native Holehe/H8mail
        # adapters; the BREACH_HIT itself remains terminal and is never a seed.
        seen_emails: set[str] = set()
        for email in _EMAIL_RE.findall(data):
            normalized = email.lower()
            if normalized in seen_emails:
                continue
            seen_emails.add(normalized)
            add(
                EntityType.EMAIL,
                normalized,
                {"record_type": "email", "from_leak_content": True},
                notes=["email extracted from LEAKSITE_CONTENT"],
            )
    elif event_type in {"LEAKSITE_URL", "DARKNET_MENTION_URL", "LINKED_URL_INTERNAL", "LINKED_URL_EXTERNAL",
                        "URL_FORM", "URL_STATIC", "URL_JAVASCRIPT", "URL_UPLOAD", "URL_PASSWORD", "URL_FLASH"}:
        add(EntityType.URL, data, {"record_type": "url"})
    elif event_type == "HUMAN_NAME":
        add(EntityType.PERSON, data, {"record_type": "person_name"})
    elif event_type == "COMPANY_NAME":
        add(EntityType.COMPANY, data, {"record_type": "company_name"})
    elif event_type in {"PHYSICAL_ADDRESS", "GEOINFO"}:
        add(EntityType.PLACE if event_type == "PHYSICAL_ADDRESS" else EntityType.GEOLOCATION,
            data, {"record_type": "location"})
    elif event_type in {"PHYSICAL_COORDINATES"}:
        add(EntityType.GEOLOCATION, data, {"record_type": "coordinates"})
    elif event_type in {"BITCOIN_ADDRESS", "ETHEREUM_ADDRESS"}:
        add(EntityType.TECHNICAL_FINDING, data, {
            "record_type": "crypto_address",
            "asset": "btc" if event_type == "BITCOIN_ADDRESS" else "eth",
        })
    elif event_type.startswith(_TECHNICAL_PREFIXES):
        mapped = _malicious_mapping(event_type)
        if mapped is not None:
            add(mapped, data, {"record_type": mapped.value, "classification": "malicious"})
        else:
            add(EntityType.TECHNICAL_FINDING, f"{event_type.lower()}:{data}", {
                "record_type": "malicious_indicator",
                "raw_data": data,
            })
    elif event_type in {
        "TCP_PORT_OPEN", "PROVIDER_TELCO", "PROVIDER_HOSTING", "WEBSERVER_TECHNOLOGY",
        "NETBLOCK_OWNER", "NETBLOCKV6_OWNER", "NETBLOCK_MEMBER", "NETBLOCKV6_MEMBER",
        "BGP_AS_OWNER", "BGP_AS_MEMBER", "DNS_TEXT", "SOFTWARE_USED",
    }:
        add(EntityType.TECHNICAL_FINDING, data, {
            "record_type": "technical",
            "event_type": event_type,
        })
    return out


def _skip_finding(request: AdapterRunRequest, skip: dict[str, Any]) -> Finding:
    module = _text(skip.get("module"), 128)
    module_meta = _module_meta(module)
    raw = json.dumps(skip, sort_keys=True, default=str).encode("utf-8", "replace")
    reason = _text(skip.get("reason"), 500) or "source skipped"
    return Finding(
        entity_type=EntityType.TECHNICAL_FINDING,
        value=f"spiderfoot:{module}:skipped",
        attributes={
            "source": "spiderfoot",
            "data_source": module_meta.get("source"),
            "spiderfoot_module": module,
            "legal_tier": module_meta.get("legal_tier"),
            "legal_tier_label": module_meta.get("legal_label"),
            "source_priority": "secondary",
            "details": {
                "skipped": True,
                "reason": reason,
                "env": _text(skip.get("env"), 128),
                "requires_key": bool(skip.get("requires_key")),
            },
        },
        provenance=Provenance(
            tool="spiderfoot",
            source_url=str(module_meta.get("website") or "https://github.com/smicallef/spiderfoot"),
            confidence=1.0,
            raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
            adapter_version=f"{SPIDERFOOT_VERSION} ({SPIDERFOOT_COMMIT[:12]})",
            seed_index=request.seed_index,
            notes=[f"SpiderFoot module {module} was skipped: {reason}"],
        ),
        source_kind="source_status",
        source_priority="secondary",
    )


def _run_status(payload: dict[str, Any], exit_code: int, parse_error: str | None) -> str:
    if parse_error:
        return "partial"
    status = _text(payload.get("status"), 32).lower()
    errors = payload.get("errors")
    if exit_code != 0 or status == "failed":
        return "failed" if status == "failed" else "partial"
    if status == "partial" or (isinstance(errors, list) and errors):
        return "partial"
    return "succeeded"


class SpiderFootAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="spiderfoot",
        license=(
            "SpiderFoot v4.0.0 is GPL-3.0; the curated data sources retain their "
            "own terms and API policies. Aletheia's image and runner are separate "
            "original code."
        ),
        input_types=[SeedType.DOMAIN, SeedType.IP, SeedType.EMAIL, SeedType.USERNAME, SeedType.PHONE],
        output_types=[
            EntityType.DOMAIN, EntityType.HOST, EntityType.IP, EntityType.EMAIL,
            EntityType.USERNAME, EntityType.URL, EntityType.PERSON, EntityType.COMPANY,
            EntityType.PHONE, EntityType.PLACE, EntityType.GEOLOCATION,
            EntityType.BREACH_HIT, EntityType.TECHNICAL_FINDING,
        ],
        legal_notes=[
            "Curated 14-module SpiderFoot batch. Module legal tiers are recorded as "
            "descriptive metadata only; the runner does not block a module because of "
            "its tier. The operator remains responsible for authorization, source terms, "
            "quotas, and the decision to enable commercial or leak-index modules.",
            "Tier-4 modules (Intelligence X, C99, Have I Been Pwned) are leak-index or "
            "commercial sources and run only when their explicit API key is present. "
            "The adapter requires an authorization assertion; absent keys produce an "
            "explicit skip record, never a silent gap.",
            "No CAPTCHA, Cloudflare, login, OAuth, or paywall bypass is implemented. No "
            "leaked credential is used to authenticate anywhere. LEAKSITE_CONTENT is "
            "stored as a terminal breach-hit observation, not as a search seed.",
            "All SpiderFoot findings are secondary evidence. Native adapters remain the "
            "source of record, and a native attribute wins a merge conflict.",
        ],
        rate_limit=(
            "One curated SpiderFoot batch per seed with at most 14 modules; no retry "
            "loop, pagination, or module discovery. Keyed modules obey their own quotas "
            "and are skipped when the key is absent. See docker/spiderfoot/MODULES.md."
        ),
        invocation=(
            "Docker runner: python3 sf.py -s <seed> -t <spiderfoot-event-type> "
            "-o json -q -m <curated-modules>"
        ),
        version_pin=f"{SPIDERFOOT_VERSION} ({SPIDERFOOT_COMMIT})",
        upstream="https://github.com/smicallef/spiderfoot",
        network_required=True,
        docker_image="aletheia/spiderfoot:v4.0",
        output_schema={
            "finding_type": "Finding",
            "item_type": "object",
            "envelope": {
                "source": "string",
                "status": "ok|partial|failed",
                "seed": "object",
                "modules_run": "array",
                "skipped": "array",
                "events": "array",
                "errors": "array",
            },
        },
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "EMAILREP_API_KEY", "HUNTER_API_KEY", "PULSEDIVE_API_KEY",
            "INTELX_API_KEY", "C99_API_KEY", "HIBP_API_KEY",
        ],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in self.descriptor.input_types

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        seed_value = request.seed.value.strip()
        if not seed_value:
            raise ValueError("SpiderFoot seed value is empty")
        return [f"{request.seed.type.value}:{seed_value}"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str,
              stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode("utf-8", "replace")
        payload: dict[str, Any] = {}
        events: list[dict[str, Any]] = []
        parse_error: str | None = None
        skipped: list[dict[str, Any]] = []
        envelope_errors: list[Any] = []

        try:
            decoded = json.loads(stdout) if stdout.strip() else None
        except json.JSONDecodeError as exc:
            decoded = None
            parse_error = f"SpiderFoot runner output was not valid JSON: {exc.msg}"

        if isinstance(decoded, list):
            events = [item for item in decoded if isinstance(item, dict)]
        elif isinstance(decoded, dict):
            payload = decoded
            raw_events = payload.get("events")
            if isinstance(raw_events, list):
                events = [item for item in raw_events if isinstance(item, dict)]
            raw_skipped = payload.get("skipped")
            if isinstance(raw_skipped, list):
                skipped = [item for item in raw_skipped if isinstance(item, dict)]
            if isinstance(payload.get("errors"), list):
                envelope_errors = payload["errors"]
        elif decoded is not None and parse_error is None:
            parse_error = "SpiderFoot runner output was not an event array or envelope"

        findings: list[Finding] = []
        for event in events:
            for entity_type, value, attributes, notes in _map_event(event):
                findings.append(_finding(request, event, _module_meta(_text(event.get("module"), 128)),
                                         entity_type, value, attributes, notes))
        for skip in skipped:
            findings.append(_skip_finding(request, skip))

        if parse_error or envelope_errors or (isinstance(payload.get("errors"), list) and payload["errors"]):
            details = [str(item) for item in envelope_errors[:10]]
            if parse_error:
                details.insert(0, parse_error)
            findings.append(Finding(
                entity_type=EntityType.TECHNICAL_FINDING,
                value="spiderfoot:run:errors",
                attributes={
                    "source": "spiderfoot",
                    "source_priority": "secondary",
                    "details": {"errors": details},
                },
                provenance=Provenance(
                    tool="spiderfoot",
                    source_url=self.descriptor.upstream,
                    confidence=1.0,
                    raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
                    adapter_version=self.descriptor.version_pin,
                    seed_index=request.seed_index,
                    notes=["SpiderFoot run emitted errors or unusable output"],
                ),
                source_kind="derived",
                source_priority="secondary",
            ))

        status = _run_status(payload, exit_code, parse_error)
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status=status,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=_text(payload.get("stderr_tail"), 4000) if payload else stderr[-4000:],
            stdout_tail=stdout[-4000:],
            error=parse_error,
        )
