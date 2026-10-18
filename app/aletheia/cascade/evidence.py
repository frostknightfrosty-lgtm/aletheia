"""Claim-pair evidence mapping (Phase 17, P17.4).

Turns a pair of normalized claims into :class:`EvidenceItem` values per the
section 6.2 table. The mapping is a reviewable decision table, stated here in
one place:

| Observation | Class | Note |
| --- | --- | --- |
| identical email | HARD | rare identifier |
| identical phone | HARD | rare identifier |
| identical username / handle | STRONG | a reused handle is strong, not cryptographic |
| identical profile URL | STRONG | explicit cross-platform declaration |
| identical personal domain | STRONG | public mail domains and shared-platform hosts yield nothing |
| identical crypto address | STRONG | rare identifier; wallets can be shared |
| identical VIN | STRONG | binds the same asset |
| identical media sha256 | STRONG | "identical media asset hash" |
| avatar pHash match | STRONG (weight 0.8) | local-only perceptual match, requires a cheap hash to agree too |
| name variant / near-identical name | MEDIUM (weight 0.8-1.0) | nickname expansion, then Jaro-Winkler >= 0.92 |
| identical company name | MEDIUM (weight 0.6) | companies share names |
| shared personal mail domain | MEDIUM (weight 0.5) | applies within email claims and across email/domain/host claims |
| similar name (0.85 <= JW < 0.92) | WEAK (weight 0.5) | "common-name similarity" |
| identical IP | WEAK (weight 0.5) | infrastructure is shared |
| identical breach record | WEAK (weight 0.5) | aggregators echo each other |
| same personal host, different path | WEAK (weight 0.4) | one site, two pages |
| conflicting name-class claims | VETO | variant-inequivalent and JW < 0.5 (v1 conflict rule) |
| conflicting VINs | VETO | one vehicle, one VIN |

Deliberate non-evidence (shared infrastructure is expected by chance, so it
produces no item at all): equality on public mail domains, equality on
shared-platform hosts, bare file-path equality (a path string is not media
identity — use the sha256/pHash attributes), and numeric IP equality beyond
the WEAK item.

"Independent" evidence origins are built from adapter + seed slot + claim
type, so two echoes of the same observation never count twice.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from aletheia.cascade.claims import Claim
from aletheia.cascade.matching import fold_diacritics, jaro_winkler, names_equivalent
from aletheia.cascade.phash import ImageHashes, is_match
from aletheia.cascade.scoring import EvidenceClass, EvidenceItem
from aletheia.cascade.seeds import is_crypto_address, is_url_like, is_vin_like
from aletheia.core.models import EntityType

__all__ = ["PUBLIC_EMAIL_DOMAINS", "SHARED_PLATFORM_HOSTS", "compare_claims"]

# Curated shared-infrastructure data (extend as calibration data arrives).
PUBLIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
        "msn.com", "yahoo.com", "ymail.com", "icloud.com", "me.com", "mac.com",
        "proton.me", "protonmail.com", "pm.me", "gmx.com", "gmx.de", "gmx.net",
        "mail.com", "aol.com", "zoho.com", "qq.com", "163.com", "126.com",
        "mail.ru", "yandex.ru", "yandex.com", "tutanota.com", "tuta.io",
        "fastmail.com", "hey.com", "web.de", "seznam.cz", "orange.fr",
        "laposte.net", "free.fr", "libero.it", "virgilio.it",
    }
)

SHARED_PLATFORM_HOSTS = frozenset(
    {
        "github.com", "gitlab.com", "bitbucket.org", "x.com", "twitter.com",
        "facebook.com", "instagram.com", "youtube.com", "linkedin.com",
        "reddit.com", "t.me", "telegram.org", "discord.com", "discord.gg",
        "medium.com", "tumblr.com", "pinterest.com", "tiktok.com", "twitch.tv",
        "steamcommunity.com", "vk.com", "weibo.com", "mastodon.social",
        "bsky.app", "threads.net", "snapchat.com", "whatsapp.com", "signal.org",
    }
)

_NAME_TYPES = frozenset({EntityType.NAME, EntityType.PERSON})
_COMPANY_TYPES = frozenset({EntityType.COMPANY, EntityType.LEGAL_ENTITY, EntityType.LEI})


def _shared_host(host: str) -> bool:
    folded = host.casefold()
    return folded in SHARED_PLATFORM_HOSTS or folded in PUBLIC_EMAIL_DOMAINS


def _url_host(value: str) -> str | None:
    return urlsplit(value).hostname


def _claim_origin(claim: Claim) -> str:
    seed = "none" if claim.seed_index is None else str(claim.seed_index)
    return f"{claim.source_adapter}|seed={seed}|{claim.type.value}"


def _pair_origin(left: Claim, right: Claim) -> str:
    first, second = sorted((_claim_origin(left), _claim_origin(right)))
    return f"{first}~{second}"


def _domain_of(claim: Claim) -> str | None:
    """The domain a claim speaks about, when it has one."""
    if claim.type is EntityType.EMAIL and "@" in claim.value:
        return claim.value.rsplit("@", 1)[1]
    if claim.type is EntityType.DOMAIN:
        return claim.value
    if claim.type is EntityType.HOST:
        return claim.value
    if claim.type is EntityType.URL:
        return _url_host(claim.value)
    return None


def _media_evidence(left: Claim, right: Claim, origin: str) -> list[EvidenceItem]:
    left_sha = left.attributes.get("sha256")
    right_sha = right.attributes.get("sha256")
    if isinstance(left_sha, str) and left_sha and left_sha == right_sha:
        return [
            EvidenceItem(
                evidence_class=EvidenceClass.STRONG,
                reason="identical media asset (sha256)",
                origin=origin,
            )
        ]
    left_hash = left.attributes.get("phash")
    right_hash = right.attributes.get("phash")
    if isinstance(left_hash, str) and isinstance(right_hash, str):
        left_hashes = ImageHashes(
            sha256=str(left_sha or ""),
            ahash=str(left.attributes.get("ahash", "")),
            dhash=str(left.attributes.get("dhash", "")),
            phash=left_hash,
        )
        right_hashes = ImageHashes(
            sha256=str(right_sha or ""),
            ahash=str(right.attributes.get("ahash", "")),
            dhash=str(right.attributes.get("dhash", "")),
            phash=right_hash,
        )
        if left_hashes.ahash and right_hashes.ahash and left_hashes.dhash and right_hashes.dhash:
            if is_match(left_hashes, right_hashes):
                return [
                    EvidenceItem(
                        evidence_class=EvidenceClass.STRONG,
                        reason="avatar perceptual-hash match (local)",
                        origin=origin,
                        weight=0.8,
                    )
                ]
    return []


def _name_evidence(left: Claim, right: Claim, origin: str) -> list[EvidenceItem]:
    left_folded = fold_diacritics(left.value)
    right_folded = fold_diacritics(right.value)
    if names_equivalent(left_folded, right_folded):
        return [
            EvidenceItem(
                evidence_class=EvidenceClass.MEDIUM,
                reason="name variant match (nickname expansion)",
                origin=origin,
            )
        ]
    similarity = jaro_winkler(left_folded, right_folded)
    if similarity >= 0.92:
        return [
            EvidenceItem(
                evidence_class=EvidenceClass.MEDIUM,
                reason="near-identical name (Jaro-Winkler >= 0.92)",
                origin=origin,
                similarity=similarity,
                weight=0.8,
            )
        ]
    if similarity >= 0.85:
        return [
            EvidenceItem(
                evidence_class=EvidenceClass.WEAK,
                reason="similar name (common-name similarity)",
                origin=origin,
                similarity=similarity,
                weight=0.5,
            )
        ]
    if similarity < 0.5:
        return [
            EvidenceItem(
                evidence_class=EvidenceClass.VETO,
                reason="conflicting name-class claims (variant-inequivalent, JW < 0.5)",
                origin=origin,
                similarity=similarity,
            )
        ]
    return []


def _same_type_evidence(left: Claim, right: Claim, origin: str) -> list[EvidenceItem]:
    kind = left.type
    left_value = left.value
    right_value = right.value
    if kind is EntityType.EMAIL:
        if left_value == right_value:
            return [EvidenceItem(EvidenceClass.HARD, "identical email address", origin)]
        left_domain = left_value.rsplit("@", 1)[-1]
        right_domain = right_value.rsplit("@", 1)[-1]
        if left_domain == right_domain and not _shared_host(left_domain):
            return [
                EvidenceItem(
                    EvidenceClass.MEDIUM,
                    "shared personal mail domain",
                    origin,
                    weight=0.5,
                )
            ]
        return []
    if kind is EntityType.PHONE:
        if left_value == right_value:
            return [EvidenceItem(EvidenceClass.HARD, "identical phone number", origin)]
        return []
    if kind is EntityType.USERNAME:
        if left_value == right_value:
            return [EvidenceItem(EvidenceClass.STRONG, "identical username", origin)]
        return []
    if kind is EntityType.URL:
        if left_value == right_value:
            return [EvidenceItem(EvidenceClass.STRONG, "identical profile url", origin)]
        left_host = _url_host(left_value)
        right_host = _url_host(right_value)
        if left_host and left_host == right_host and not _shared_host(left_host):
            return [
                EvidenceItem(
                    EvidenceClass.WEAK,
                    "same personal host, different path",
                    origin,
                    weight=0.4,
                )
            ]
        return []
    if kind is EntityType.DOMAIN:
        if left_value == right_value and not _shared_host(left_value):
            return [EvidenceItem(EvidenceClass.STRONG, "same personal domain", origin)]
        return []
    if kind is EntityType.IP:
        if left_value == right_value:
            return [
                EvidenceItem(EvidenceClass.WEAK, "identical ip address", origin, weight=0.5)
            ]
        return []
    if kind is EntityType.BLOCKCHAIN_INTEL_RECORD:
        if left_value == right_value and is_crypto_address(left_value):
            return [EvidenceItem(EvidenceClass.STRONG, "identical crypto address", origin)]
        if left_value == right_value and is_url_like(left_value):
            return [
                EvidenceItem(EvidenceClass.STRONG, "identical profile url (blockchain record)", origin)
            ]
        return []
    if kind is EntityType.TRANSPORT_ASSET_RECORD:
        if is_vin_like(left_value) and is_vin_like(right_value):
            if left_value.strip().upper() == right_value.strip().upper():
                return [EvidenceItem(EvidenceClass.STRONG, "identical vin (same asset)", origin)]
            return [EvidenceItem(EvidenceClass.VETO, "conflicting vin", origin)]
        return []
    if kind in _NAME_TYPES:
        return _name_evidence(left, right, origin)
    if kind in _COMPANY_TYPES:
        if left_value == right_value:
            return [
                EvidenceItem(
                    EvidenceClass.MEDIUM,
                    "identical company name",
                    origin,
                    weight=0.6,
                )
            ]
        similarity = jaro_winkler(
            fold_diacritics(left_value), fold_diacritics(right_value)
        )
        if similarity >= 0.95:
            return [
                EvidenceItem(
                    EvidenceClass.WEAK,
                    "near-identical company name",
                    origin,
                    similarity=similarity,
                    weight=0.5,
                )
            ]
        return []
    if kind in (EntityType.IMAGE, EntityType.FILE):
        return _media_evidence(left, right, origin)
    if kind is EntityType.BREACH:
        if left_value == right_value:
            return [
                EvidenceItem(
                    EvidenceClass.WEAK, "identical breach record", origin, weight=0.5
                )
            ]
        return []
    return []


def _cross_type_evidence(left: Claim, right: Claim, origin: str) -> list[EvidenceItem]:
    """Cross-type rules: the shared-domain bridge (email <-> domain/host/url)."""
    left_domain = _domain_of(left)
    right_domain = _domain_of(right)
    if (
        left_domain
        and right_domain
        and left_domain == right_domain
        and not _shared_host(left_domain)
    ):
        return [
            EvidenceItem(
                EvidenceClass.MEDIUM,
                "shared personal domain (email <-> host bridge)",
                origin,
                weight=0.5,
            )
        ]
    return []


def compare_claims(left: Claim, right: Claim) -> list[EvidenceItem]:
    """The evidence items for one claim pair (empty when the pair says nothing)."""
    if left.claim_id == right.claim_id:
        raise ValueError("compare_claims expects two distinct claims")
    origin = _pair_origin(left, right)
    if left.type is right.type:
        return _same_type_evidence(left, right, origin)
    return _cross_type_evidence(left, right, origin)
