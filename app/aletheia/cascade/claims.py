"""Claim layer: normalization, dedup, and strong-key blocking (Phase 17, P17.3).

Design of record: ``docs/PIVOT_CASCADE.md`` section 5.

- A ``Claim`` is the normalized unit the cascade compares: type, canonical
  value, source, observation time, confidence, evidence hash, seed/finding
  provenance, and an Admiralty source grade (ungraded claims are F6 — the
  honest default; nothing guesses a grade it does not have).
- **Blocking** generates candidate comparison pairs only within strong-key
  blocks (shared email, phone, domain, or exact handle). This keeps
  comparisons out of O(n^2) and stops coincidence-chained false links from
  weak keys.
- Emails contribute their own address as a strong key but not their mail
  domain (a gmail.com block would otherwise merge everything); URL claims
  contribute only their host; host claims that are bare IP literals
  contribute nothing (IPs are shared infrastructure, not identity keys).
- Oversized blocks are never silently dropped: pair generation is skipped
  above ``max_block_size`` and the key is reported in ``oversized_blocks``.
- Conflict records and union-find propagation land with P17.5; this module
  produces the normalized claims, blocks, and candidate pairs only.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from aletheia.cascade.seeds import canonicalize_seed, is_domain_like, is_handle_like, is_url_like
from aletheia.core.models import EntityType, Finding, Seed, SeedType, SourceGrade, utc_now

__all__ = [
    "BlockingResult",
    "Claim",
    "block_claims",
    "claim_from_finding",
    "claim_origin_key",
    "dedupe_claims",
    "normalize_claim_value",
    "pair_origin_key",
    "strong_keys",
]

_SEED_BACKED_TYPES: dict[EntityType, SeedType] = {
    EntityType.URL: SeedType.URL,
    EntityType.DOMAIN: SeedType.DOMAIN,
    EntityType.EMAIL: SeedType.EMAIL,
    EntityType.USERNAME: SeedType.USERNAME,
    EntityType.IP: SeedType.IP,
    EntityType.PHONE: SeedType.PHONE,
    EntityType.HOST: SeedType.DOMAIN,
}


def _strip_port(value: str) -> str:
    if value.startswith("["):
        return value
    if value.count(":") != 1:
        return value
    host, _, port = value.partition(":")
    if host and port.isdigit():
        return host
    return value


class Claim(BaseModel):
    """A normalized claim (design section 5)."""

    model_config = ConfigDict(extra="forbid")
    claim_id: UUID = Field(default_factory=uuid4)
    type: EntityType
    value: str
    source_adapter: str
    source_url: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_evidence_sha256: str | None = None
    seed_index: int | None = None
    finding_id: UUID
    parent_finding_id: UUID | None = None
    source_grade: SourceGrade = Field(default_factory=SourceGrade.unrated)
    attributes: dict[str, Any] = Field(default_factory=dict)


def normalize_claim_value(entity_type: EntityType, value: str) -> str:
    """Canonicalize a claim value for dedup and comparison.

    Seed-backed types (URL, DOMAIN, EMAIL, USERNAME, IP, PHONE, HOST) reuse
    :func:`aletheia.cascade.seeds.canonicalize_seed`; host values are
    port-stripped first. Every other type collapses whitespace only — the
    cascade never rewrites a name, record, or free-text value it cannot
    validate.
    """
    if entity_type is EntityType.HOST:
        value = _strip_port(value.strip())
    seed_type = _SEED_BACKED_TYPES.get(entity_type)
    if seed_type is not None:
        return canonicalize_seed(Seed(type=seed_type, value=value)).value
    return " ".join(value.split())


def claim_from_finding(finding: Finding) -> Claim:
    """Build a normalized claim from an adapter finding and its provenance."""
    provenance = finding.provenance
    return Claim(
        type=finding.entity_type,
        value=normalize_claim_value(finding.entity_type, finding.value),
        source_adapter=provenance.tool,
        source_url=provenance.source_url,
        observed_at=provenance.observed_at,
        confidence=provenance.confidence,
        raw_evidence_sha256=provenance.raw_evidence_sha256,
        seed_index=provenance.seed_index,
        finding_id=finding.finding_id,
        parent_finding_id=provenance.parent_finding_id,
        attributes=dict(finding.attributes),
    )


def dedupe_claims(claims: Iterable[Claim]) -> list[Claim]:
    """Drop duplicates (same type + value) keeping first appearance."""
    seen: set[tuple[EntityType, str]] = set()
    result: list[Claim] = []
    for claim in claims:
        key = (claim.type, claim.value)
        if key in seen:
            continue
        seen.add(key)
        result.append(claim)
    return result


def claim_origin_key(claim: Claim) -> str:
    """The independence key of one claim: adapter + seed slot + claim type.

    Two echoes of the same observation share this key, so tier counting can
    collapse them; distinct adapters or claim types stay independent.
    """
    seed = "none" if claim.seed_index is None else str(claim.seed_index)
    return f"{claim.source_adapter}|seed={seed}|{claim.type.value}"


def pair_origin_key(left: Claim, right: Claim) -> str:
    """A deterministic origin for evidence derived from one claim pair."""
    first, second = sorted((claim_origin_key(left), claim_origin_key(right)))
    return f"{first}~{second}"


def strong_keys(claim: Claim) -> frozenset[str]:
    """The strong blocking keys a claim contributes (design section 5).

    Kinds: ``email:``, ``phone:``, ``domain:``, ``username:``. Weak
    coincidences (an IP address, a mail domain, an account URL's host) are
    deliberately not keys.
    """
    keys: set[str] = set()
    kind = claim.type
    value = claim.value
    if kind is EntityType.EMAIL:
        keys.add(f"email:{value}")
    elif kind is EntityType.PHONE:
        keys.add(f"phone:{value}")
    elif kind is EntityType.DOMAIN:
        keys.add(f"domain:{value}")
    elif kind is EntityType.HOST:
        try:
            ipaddress.ip_address(value)
        except ValueError:
            keys.add(f"domain:{value}")
    elif kind is EntityType.URL:
        host = urlsplit(value).hostname
        if host:
            keys.add(f"domain:{host}")
    elif kind is EntityType.USERNAME:
        keys.add(f"username:{value}")
    elif kind is EntityType.SOCIAL_ACCOUNT and is_handle_like(value) and not is_url_like(value):
        keys.add(f"username:{value.lstrip('@').lower()}")
    elif kind is EntityType.EMAIL_AUTH_RECORD and is_domain_like(value):
        keys.add(f"domain:{value}")
    return frozenset(keys)


@dataclass(frozen=True)
class BlockingResult:
    """Blocks and the candidate pairs generated from them.

    ``pairs`` is deterministically ordered; ``oversized_blocks`` lists the
    keys whose pair generation was skipped (key, claim count).
    """

    blocks: Mapping[str, tuple[UUID, ...]]
    pairs: tuple[tuple[UUID, UUID], ...]
    oversized_blocks: tuple[tuple[str, int], ...]


def block_claims(claims: Sequence[Claim], max_block_size: int = 512) -> BlockingResult:
    """Generate comparison candidate pairs within strong-key blocks only."""
    if max_block_size < 1:
        raise ValueError("max_block_size must be >= 1")
    key_to_ids: dict[str, list[UUID]] = {}
    for claim in claims:
        for key in strong_keys(claim):
            key_to_ids.setdefault(key, []).append(claim.claim_id)
    blocks: dict[str, tuple[UUID, ...]] = {}
    oversized: list[tuple[str, int]] = []
    pair_set: set[tuple[UUID, UUID]] = set()
    for key in sorted(key_to_ids):
        ids = key_to_ids[key]
        blocks[key] = tuple(ids)
        if len(ids) > max_block_size:
            oversized.append((key, len(ids)))
            continue
        for left, right in combinations(ids, 2):
            pair_set.add((left, right) if str(left) <= str(right) else (right, left))
    pairs = tuple(sorted(pair_set, key=lambda pair: (str(pair[0]), str(pair[1]))))
    return BlockingResult(blocks=blocks, pairs=pairs, oversized_blocks=tuple(oversized))
