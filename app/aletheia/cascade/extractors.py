"""Pivot extractors: claims -> typed candidate seeds (Phase 17, P17.3).

Design of record: ``docs/PIVOT_CASCADE.md`` sections 4.1 (bridge claims) and 7
(pivot extraction and gates).

- Every rule emits seed candidates inside the claim's bridge set
  (:data:`aletheia.cascade.routing.BRIDGE_SEED_TYPES`); text-bearing claims
  (OCR text, technical findings) run seed autodetection instead. The
  build-time test walks every ``EntityType`` and asserts exactly that, and
  ``extract_pivots`` raises if a rule ever drifts outside its map.
- Gates follow section 7's policy: personal identifiers (email, phone, person
  names, declared location) require a **confirmed** origin cluster; structural
  and media seeds require **probable**+. ``possible``/``excluded`` spawn
  nothing — enforcement happens where cluster tiers exist (P17.4+); this
  module only labels the gate on each candidate.
- Ambiguous record parties (court cases, sanctions, filings, registry and IP
  records) yield the generic ``name`` seed class: the record does not say
  whether the party is a person or an organization, and the cascade does not
  guess. Place *names* are not geocoded here (no honest local geocoder);
  coordinate-like values pass through, names wait for an adapter.
- ``extract_pivots`` never runs an adapter and never touches the network.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from aletheia.cascade.claims import Claim
from aletheia.cascade.routing import BRIDGE_SEED_TYPES, TEXT_AUTODETECT_ENTITY_TYPES
from aletheia.cascade.seeds import (
    canonicalize_seed,
    detect_seeds,
    find_domain_like,
    is_crypto_address,
    is_domain_like,
    is_email_like,
    is_handle_like,
    is_url_like,
    is_vin_like,
)
from aletheia.core.models import EntityType, IdentityTier, PivotCandidate, Seed, SeedType

__all__ = ["EXTRACTOR_RULES", "extract_pivots", "gate_for"]

# Section 7 policy: these seed classes are personal (or a declared location)
# and pivot only from a confirmed cluster; everything else needs probable+.
_CONFIRMED_GATE_TYPES = frozenset(
    {
        SeedType.EMAIL,
        SeedType.PHONE,
        SeedType.PERSON_NAME,
        SeedType.NAME,
        SeedType.GEOLOCATION,
    }
)

_COORDINATE_RE = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*(?:,|\s)\s*(-?\d{1,3}(?:\.\d+)?)\s*$")

_RuleResult = list[tuple[SeedType, str, str]]
_Rule = Callable[[str, dict[str, Any]], _RuleResult]


def gate_for(seed_type: SeedType) -> IdentityTier:
    """The minimum surviving cluster tier that permits this seed class."""
    if seed_type in _CONFIRMED_GATE_TYPES:
        return IdentityTier.CONFIRMED
    return IdentityTier.PROBABLE


def _coordinate(value: str) -> str | None:
    match = _COORDINATE_RE.match(value)
    if match is None:
        return None
    latitude = float(match.group(1))
    longitude = float(match.group(2))
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return f"{latitude},{longitude}"


def _url_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    out: _RuleResult = [(SeedType.URL, value, "url claim yields itself")]
    host = urlsplit(value).hostname
    if host:
        out.append((SeedType.DOMAIN, host, "url claim yields its host"))
    return out


def _domain_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    domain = canonicalize_seed(Seed(type=SeedType.DOMAIN, value=value)).value
    return [
        (SeedType.DOMAIN, domain, "domain claim yields itself"),
        (SeedType.URL, f"https://{domain}", "domain claim yields its canonical https url"),
    ]


def _host_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    try:
        return [(SeedType.IP, str(ipaddress.ip_address(value)), "host claim is an ip literal")]
    except ValueError:
        return [(SeedType.DOMAIN, value, "host claim yields its domain")]


def _email_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    out: _RuleResult = [(SeedType.EMAIL, value, "email claim yields itself")]
    if "@" in value:
        domain = value.rsplit("@", 1)[1]
        if is_domain_like(domain):
            out.append((SeedType.DOMAIN, domain, "email claim yields its domain"))
    return out


def _username_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.USERNAME, value, "handle claim yields its username")]


def _ip_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.IP, value, "ip claim yields itself")]


def _phone_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.PHONE, value, "phone claim yields itself")]


def _file_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.FILE_PATH, value, "file claim yields its path")]


def _image_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [
        (SeedType.IMAGE, value, "media asset yields its image seed"),
        (SeedType.FILE_PATH, value, "media asset yields its path"),
    ]


def _person_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.PERSON_NAME, value, "declared person name yields its person-name seed")]


def _name_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.NAME, value, "name-class claim yields a generic name seed")]


def _company_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.COMPANY_NAME, value, "company claim yields its company-name seed")]


def _party_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.NAME, value, "record party name yields a generic name seed (kind unknown)")]


def _academic_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [(SeedType.PERSON_NAME, value, "academic record yields its author name")]


def _social_account_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    if is_url_like(value):
        return [(SeedType.URL, value, "account url yields its url")]
    if is_handle_like(value):
        return [(SeedType.USERNAME, value, "account handle yields its username")]
    return []


def _breach_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    if is_email_like(value):
        out: _RuleResult = [(SeedType.EMAIL, value, "breach record yields its email")]
        domain = value.rsplit("@", 1)[1]
        if is_domain_like(domain):
            out.append((SeedType.DOMAIN, domain, "breach record yields its email domain"))
        return out
    domain = find_domain_like(value)
    if domain:
        return [(SeedType.DOMAIN, domain, "breach record yields its domain")]
    return []


def _tls_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    try:
        return [
            (SeedType.IP, str(ipaddress.ip_address(value)), "tls observation yields its ip literal")
        ]
    except ValueError:
        pass
    domain = find_domain_like(value)
    if domain:
        return [(SeedType.DOMAIN, domain, "tls observation yields its host")]
    return []


def _blockchain_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    if is_crypto_address(value):
        return [(SeedType.CRYPTO_ADDRESS, value, "blockchain intel yields its address")]
    if is_url_like(value):
        return [(SeedType.URL, value, "blockchain intel yields its url")]
    return []


def _email_auth_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    domain = find_domain_like(value)
    if domain:
        return [(SeedType.DOMAIN, domain, "email auth record yields its domain")]
    return []


def _text_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    return [
        (seed.type, seed.value, "text autodetection")
        for seed in detect_seeds(value)
    ]


def _technical_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    allowed = BRIDGE_SEED_TYPES[EntityType.TECHNICAL_FINDING]
    return [
        (seed.type, seed.value, "technical finding text autodetection")
        for seed in detect_seeds(value)
        if seed.type in allowed
    ]


def _web_search_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    if is_url_like(value):
        out: _RuleResult = [(SeedType.URL, value, "search result yields its url")]
        host = urlsplit(value).hostname
        if host:
            out.append((SeedType.DOMAIN, host, "search result url yields its host"))
        return out
    domain = find_domain_like(value)
    if domain:
        return [(SeedType.DOMAIN, domain, "search result yields its domain")]
    return []


def _geo_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    coordinate = _coordinate(value)
    if coordinate is None:
        return []
    return [
        (
            SeedType.GEOLOCATION,
            coordinate,
            "geo evidence yields its coordinates (declared location, low priority)",
        )
    ]


def _place_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    coordinate = _coordinate(value)
    if coordinate is None:
        # A place name needs a geocoder; the cascade does not invent coordinates.
        return []
    return [(SeedType.GEOLOCATION, coordinate, "place claim was already coordinate-like")]


def _transport_rule(value: str, attributes: dict[str, Any]) -> _RuleResult:
    if is_vin_like(value):
        return [(SeedType.VIN, value.strip().upper(), "transport record yields its vin")]
    return []


EXTRACTOR_RULES: dict[EntityType, _Rule] = {
    EntityType.URL: _url_rule,
    EntityType.DOMAIN: _domain_rule,
    EntityType.HOST: _host_rule,
    EntityType.EMAIL: _email_rule,
    EntityType.USERNAME: _username_rule,
    EntityType.IP: _ip_rule,
    EntityType.PHONE: _phone_rule,
    EntityType.FILE: _file_rule,
    EntityType.IMAGE: _image_rule,
    EntityType.PERSON: _person_rule,
    EntityType.NAME: _name_rule,
    EntityType.COMPANY: _company_rule,
    EntityType.LEGAL_ENTITY: _company_rule,
    EntityType.LEI: _company_rule,
    EntityType.FILING: _party_rule,
    EntityType.COURT_CASE: _party_rule,
    EntityType.SANCTION: _party_rule,
    EntityType.GOVERNMENT_RECORD: _party_rule,
    EntityType.COMPANY_REGISTRY_RECORD: _party_rule,
    EntityType.INTELLECTUAL_PROPERTY_RECORD: _party_rule,
    EntityType.ACADEMIC_RECORD: _academic_rule,
    EntityType.SOCIAL_ACCOUNT: _social_account_rule,
    EntityType.BREACH: _breach_rule,
    EntityType.TLS_OBSERVATION: _tls_rule,
    EntityType.BLOCKCHAIN_INTEL_RECORD: _blockchain_rule,
    EntityType.EMAIL_AUTH_RECORD: _email_auth_rule,
    EntityType.TECHNICAL_FINDING: _technical_rule,
    EntityType.WEB_SEARCH_RESULT: _web_search_rule,
    EntityType.GEOLOCATION: _geo_rule,
    EntityType.GEO_EVIDENCE: _geo_rule,
    EntityType.PLACE: _place_rule,
    EntityType.TRANSPORT_ASSET_RECORD: _transport_rule,
    EntityType.OCR_TEXT: _text_rule,
}


def extract_pivots(claim: Claim) -> list[PivotCandidate]:
    """Derive typed pivot candidates from one claim (deduplicated, ordered)."""
    rule = EXTRACTOR_RULES.get(claim.type)
    if rule is None:
        return []
    if claim.type in TEXT_AUTODETECT_ENTITY_TYPES:
        allowed = frozenset(SeedType)
    else:
        allowed = BRIDGE_SEED_TYPES.get(claim.type, frozenset())
    candidates: list[PivotCandidate] = []
    seen: set[tuple[SeedType, str]] = set()
    for seed_type, raw_value, reason in rule(claim.value, dict(claim.attributes)):
        if seed_type not in allowed:
            raise AssertionError(
                f"extractor for {claim.type.value} emitted {seed_type.value}, "
                "which is outside its bridge map"
            )
        if not raw_value.strip():
            continue
        seed = canonicalize_seed(Seed(type=seed_type, value=raw_value))
        key = (seed.type, seed.value)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            PivotCandidate(
                claim_entity_type=claim.type,
                claim_value=claim.value,
                seed=seed,
                gate=gate_for(seed.type),
                reason=reason,
                seed_index=claim.seed_index,
                parent_finding_id=claim.finding_id,
            )
        )
    return candidates
