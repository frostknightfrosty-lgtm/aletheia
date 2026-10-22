"""Profile-level exponential linking (Phase 18.1).

The Phase 17 resolver compares canonical values (handles, names, domains).
Phase 18.1 adds three profile-level signals that are independent of the
canonical string:

- **Avatar pHash** -- acquire the public avatar (through the egress proxy),
  compute the project's 64-bit pHash, and accept a Hamming distance of at most
  :data:`AVATAR_PHASH_MAX_DISTANCE` as a confirmed same-person link.
- **Network overlap** -- Jaccard similarity over the public connection lists;
  ``>= 0.40`` is a confirmed link.
- **Temporal cadence** -- the pure histogram comparison lives in
  :mod:`aletheia.cascade.scoring`; this module only extracts the public
  timestamps that feed it.

Everything here is either a pure extractor or an explicitly injected network
boundary (``avatar_fetcher`` / ``profile_enricher``). The default fetcher uses
``HTTP(S)_PROXY`` when present and never follows a URL into a private address.
No adapter is hard-coded here: if a profile adapter did not capture an avatar,
the resolver passes an adapter-backed ``profile_enricher`` callback and records
that it asked the adapter for the missing field.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

from aletheia.cascade.matching import fold_diacritics, jaccard_similarity, jaro_winkler
from aletheia.cascade.phash import ImageHashes, hash_ensemble, hamming_text
from aletheia.cascade.scoring import (
    TEMPORAL_OVERLAP_THRESHOLD,
    TemporalCadence,
    compare_activity_histograms,
)
from aletheia.core.models import RelationshipType

__all__ = [
    "AVATAR_CONFIDENCE",
    "AVATAR_PHASH_MAX_DISTANCE",
    "NETWORK_CONFIDENCE",
    "NETWORK_JACCARD_THRESHOLD",
    "ProfileAttributes",
    "ProfileLink",
    "ProfileLinker",
    "ProfileEnricher",
    "AvatarFetcher",
    "NetworkOverlap",
    "fetch_avatar_bytes",
    "profile_comparison_pairs",
    "profile_temporal_cadence",
]

AVATAR_PHASH_MAX_DISTANCE = 5
AVATAR_CONFIDENCE = 0.95
NETWORK_JACCARD_THRESHOLD = 0.40
NETWORK_CONFIDENCE = 0.90

# A bounded profile-pair block keeps the Phase 18.1 reachability extension from
# becoming an accidental O(n^2) comparison over every claim in a run.
PROFILE_PAIR_MAX_PROFILES = 128
PROFILE_PAIR_MAX_PAIRS = 4096
DEFAULT_AVATAR_MAX_BYTES = 5_000_000
DEFAULT_AVATAR_TIMEOUT_SECONDS = 10.0

_HEX_HASH_RE = re.compile(r"^[0-9a-fA-F]{16}$")
_PRIVATE_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")


class AvatarFetcher(Protocol):
    """The only network boundary in this module: URL -> public image bytes."""

    def __call__(self, url: str) -> bytes | None: ...


ProfileEnricher = Callable[[Any], Mapping[str, Any] | None]


class AvatarFetchError(ValueError):
    """Raised when a public avatar cannot be fetched safely."""


def _casefold_map(attributes: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).casefold(): value for key, value in attributes.items()}


def _first(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _valid_hex(value: Any) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**64:
        return f"{value:016x}"
    if isinstance(value, str) and _HEX_HASH_RE.fullmatch(value.strip()):
        return value.strip().lower()
    return None


def _phash_from(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _valid_hex(value.get("phash"))
    return _valid_hex(value)


def _url_values(value: Any) -> list[str]:
    """Flatten URL-like connection values, dropping counts and nested noise."""
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Mapping):
        for key in (
            "url",
            "profile_url",
            "value",
            "handle",
            "username",
            "login",
            "name",
            "id",
        ):
            candidate = value.get(key)
            if isinstance(candidate, (str, int)) and not isinstance(candidate, bool):
                text = str(candidate).strip()
                if text:
                    return [text]
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        out: list[str] = []
        for item in value:
            out.extend(_url_values(item))
        return out
    return []


def _normalize_connection(value: str) -> str:
    text = value.strip().casefold()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    if parsed.hostname:
        host = parsed.hostname.casefold()
        path = parsed.path.rstrip("/")
        return f"{host}{path}" if path else host
    return text.rstrip("/")


def _timestamp_values(value: Any) -> list[Any]:
    """Flatten public post/comment timestamps from common adapter shapes."""
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return [value]
    if isinstance(value, Mapping):
        out: list[Any] = []
        for key in (
            "created_at",
            "created_utc",
            "timestamp",
            "published_at",
            "posted_at",
            "date",
            "datetime",
        ):
            item = value.get(key)
            if item is not None:
                out.extend(_timestamp_values(item))
        if not out:
            for key in ("posts", "comments", "activity", "items"):
                item = value.get(key)
                if item is not None:
                    out.extend(_timestamp_values(item))
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        out: list[Any] = []
        for item in value:
            out.extend(_timestamp_values(item))
        return out
    return []


@dataclass(frozen=True)
class ProfileAttributes:
    """The profile-level fields Phase 18.1 knows how to use.

    Adapter attribute names are normalized here rather than in every adapter:
    ``icon_img``/``profile_pic_url``/``thumbnail`` all mean avatar URL, and
    ``posts``/``comments``/``activity_timestamps`` all feed the cadence.
    """

    avatar_url: str | None = None
    avatar_phash: str | None = None
    avatar_bytes: bytes | None = None
    connections: frozenset[str] = field(default_factory=frozenset)
    activity_values: tuple[Any, ...] = ()
    active_hours: tuple[int, ...] = ()
    display_name: str | None = None
    username: str | None = None
    platform: str | None = None
    profile_url: str | None = None

    @classmethod
    def from_attributes(cls, attributes: Mapping[str, Any] | None) -> "ProfileAttributes":
        raw = _casefold_map(attributes or {})
        avatar_url = _text(
            _first(
                raw,
                (
                    "avatar_url",
                    "avatar",
                    "profile_pic_url",
                    "profile_image_url",
                    "icon_img",
                    "picture",
                    "image_url",
                ),
            )
        )
        avatar_phash = _phash_from(
            _first(raw, ("avatar_phash", "avatar_hash", "avatar_phash_hex"))
        )
        if avatar_phash is None:
            avatar_phash = _phash_from(raw.get("avatar_hashes"))
        if avatar_phash is None:
            avatar_phash = _phash_from(raw.get("phash"))

        avatar_bytes = raw.get("avatar_bytes")
        if not isinstance(avatar_bytes, bytes):
            avatar_bytes = None

        connection_value = _first(
            raw,
            (
                "connections",
                "connection_urls",
                "links",
                "outbound_links",
                "followers",
                "following",
                "friends",
                "subreddits",
                "repos",
            ),
        )
        connections = frozenset(
            value
            for value in (_normalize_connection(item) for item in _url_values(connection_value))
            if value
        )

        activity_values: list[Any] = []
        for key in (
            "activity_timestamps",
            "post_timestamps",
            "comment_timestamps",
            "timestamps",
            "recent_activity",
            "posts",
            "comments",
            "activity",
        ):
            if key in raw:
                activity_values.extend(_timestamp_values(raw.get(key)))
        raw_hours = _first(raw, ("active_hours", "activity_hours"))
        if isinstance(raw_hours, int) and not isinstance(raw_hours, bool):
            raw_hours = (raw_hours,)
        elif not isinstance(raw_hours, (list, tuple, set, frozenset)):
            raw_hours = ()
        active_hours = tuple(
            int(hour)
            for hour in raw_hours
            if isinstance(hour, int) and not isinstance(hour, bool) and 0 <= hour <= 23
        )

        display_name = _text(
            _first(raw, ("display_name", "displayname", "full_name", "fullname", "name", "title"))
        )
        username = _text(
            _first(raw, ("username", "login", "handle", "screen_name", "user", "account"))
        )
        platform = _text(_first(raw, ("platform", "service", "site", "network")))
        profile_url = _text(
            _first(raw, ("profile_url", "html_url", "url", "account_url", "permalink"))
        )
        return cls(
            avatar_url=avatar_url,
            avatar_phash=avatar_phash,
            avatar_bytes=avatar_bytes,
            connections=connections,
            activity_values=tuple(activity_values),
            active_hours=active_hours,
            display_name=display_name,
            username=username,
            platform=platform.casefold() if platform else None,
            profile_url=profile_url,
        )

    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar_url or self.avatar_phash or self.avatar_bytes)

    @property
    def has_profile_data(self) -> bool:
        """True when this is a profile-shaped claim worth profile comparison."""
        return bool(
            self.has_avatar
            or self.connections
            or self.activity_values
            or self.active_hours
            or (self.platform and (self.username or self.display_name or self.profile_url))
            or (self.profile_url and (self.username or self.display_name))
        )

    @property
    def label(self) -> str:
        return self.username or self.display_name or self.profile_url or "profile"

    def timestamp_values(self) -> tuple[Any, ...]:
        if self.active_hours:
            return (*self.activity_values, *self.active_hours)
        return self.activity_values


@dataclass(frozen=True)
class NetworkOverlap:
    """Jaccard overlap over two public connection sets."""

    left: frozenset[str]
    right: frozenset[str]
    jaccard: float
    significant: bool
    threshold: float = NETWORK_JACCARD_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_count": len(self.left),
            "right_count": len(self.right),
            "jaccard": self.jaccard,
            "threshold": self.threshold,
            "significant": self.significant,
        }


@dataclass(frozen=True)
class ProfileLink:
    """A confirmed profile-level link (a graph ``SAME_AS_CONFIRMED`` edge)."""

    left_entity_id: UUID
    right_entity_id: UUID
    relationship: RelationshipType
    confidence: float
    source: str
    detail: str
    left_value: str
    right_value: str
    left_platform: str | None = None
    right_platform: str | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_entity_id": str(self.left_entity_id),
            "right_entity_id": str(self.right_entity_id),
            "relationship": self.relationship.value,
            "confidence": self.confidence,
            "source": self.source,
            "detail": self.detail,
            "left_value": self.left_value,
            "right_value": self.right_value,
            "left_platform": self.left_platform,
            "right_platform": self.right_platform,
            "metrics": dict(self.metrics),
        }


def _is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(
        _PRIVATE_HOST_SUFFIXES
    ):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def _proxy_from_environment() -> str | None:
    import os

    for key in (
        "ALETHEIA_HTTPS_PROXY",
        "ALETHEIA_HTTP_PROXY",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
    ):
        value = os.getenv(key)
        if value:
            return value
    return None


def fetch_avatar_bytes(
    url: str,
    *,
    proxy_url: str | None = None,
    timeout_seconds: float = DEFAULT_AVATAR_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_AVATAR_MAX_BYTES,
) -> bytes:
    """Fetch one public avatar, respecting the egress proxy and a byte cap.

    The request is deliberately a plain public GET: no credentials, cookies,
    CAPTCHA handling, or browser automation. A proxy URL can be supplied by the
    caller (the live wiring passes the per-adapter egress proxy); otherwise the
    standard ``HTTPS_PROXY``/``HTTP_PROXY`` environment variables are used.
    """
    import urllib.request

    if not _is_public_http_url(url):
        raise AvatarFetchError("avatar URL must be a public http(s) URL")
    proxy = proxy_url or _proxy_from_environment()
    handlers: list[Any] = []
    if proxy:
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Aletheia/0.1 (public avatar pHash; passive OSINT)",
            "Accept": "image/*",
            "X-Aletheia-Purpose": "avatar_phash",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=float(timeout_seconds)) as response:
            final_url = response.geturl()
            if not _is_public_http_url(final_url):
                raise AvatarFetchError("avatar redirect left the public web")
            declared = response.headers.get("Content-Length")
            if declared is not None:
                try:
                    if int(declared) > max_bytes:
                        raise AvatarFetchError("avatar exceeds the configured byte cap")
                except ValueError:
                    pass
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(min(64 * 1024, max_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise AvatarFetchError("avatar exceeds the configured byte cap")
                chunks.append(chunk)
    except AvatarFetchError:
        raise
    except Exception as exc:  # noqa: BLE001 - callers record the failure, never retry
        raise AvatarFetchError(f"avatar fetch failed: {exc}") from exc
    data = b"".join(chunks)
    if not data:
        raise AvatarFetchError("avatar response was empty")
    return data


class ProfileLinker:
    """Compute Phase 18.1 confirmed links and injectable profile enrichment."""

    def __init__(
        self,
        *,
        avatar_fetcher: AvatarFetcher | None = None,
        profile_enricher: ProfileEnricher | None = None,
        proxy_url: str | None = None,
        timeout_seconds: float = DEFAULT_AVATAR_TIMEOUT_SECONDS,
        max_avatar_bytes: int = DEFAULT_AVATAR_MAX_BYTES,
        enrich_missing_avatars: bool = True,
        fetch_avatars: bool = True,
    ) -> None:
        self._avatar_fetcher = avatar_fetcher
        self.profile_enricher = profile_enricher
        self.proxy_url = proxy_url
        self.timeout_seconds = float(timeout_seconds)
        self.max_avatar_bytes = int(max_avatar_bytes)
        self.enrich_missing_avatars = bool(enrich_missing_avatars)
        self.fetch_avatars = bool(fetch_avatars)
        self._hash_cache: dict[str, ImageHashes | None] = {}
        self._fetch_errors: dict[str, str] = {}
        self.enrichment_attempts: list[dict[str, Any]] = []
        self.avatar_downloads: int = 0

    @property
    def fetch_errors(self) -> Mapping[str, str]:
        return dict(self._fetch_errors)

    def _enrich(self, entity: Any) -> None:
        if self.profile_enricher is None:
            return
        attributes = getattr(entity, "attributes", None)
        if not isinstance(attributes, dict):
            return
        before = ProfileAttributes.from_attributes(attributes)
        if before.has_avatar or not self.enrich_missing_avatars:
            return
        if not (before.platform or before.username or before.profile_url):
            return
        attempt: dict[str, Any] = {
            "entity_id": str(getattr(entity, "entity_id", "")),
            "platform": before.platform,
            "username": before.username,
            "reason": "adapter did not capture avatar_url",
        }
        try:
            supplied = self.profile_enricher(entity)
        except Exception as exc:  # noqa: BLE001 - recorded, never hidden
            attempt.update({"ok": False, "error": str(exc)[:300]})
            self.enrichment_attempts.append(attempt)
            attributes["avatar_refetch"] = dict(attempt)
            return
        if isinstance(supplied, Mapping):
            for key, value in supplied.items():
                if value is not None and not attributes.get(str(key)):
                    attributes[str(key)] = value
            after = ProfileAttributes.from_attributes(attributes)
            attempt.update(
                {
                    "ok": bool(after.has_avatar),
                    "avatar_url_present": bool(after.avatar_url),
                    "keys_supplied": sorted(str(key) for key in supplied),
                }
            )
        else:
            attempt.update({"ok": False, "error": "enricher returned no attributes"})
        self.enrichment_attempts.append(attempt)
        attributes["avatar_refetch"] = dict(attempt)

    def prepare(self, entity: Any) -> ProfileAttributes:
        attributes = getattr(entity, "attributes", None)
        if not isinstance(attributes, dict):
            return ProfileAttributes.from_attributes({})
        parsed = ProfileAttributes.from_attributes(attributes)
        if not parsed.has_avatar:
            self._enrich(entity)
            parsed = ProfileAttributes.from_attributes(attributes)
        return parsed

    def _fetch(self, url: str) -> bytes | None:
        if not self.fetch_avatars:
            self._fetch_errors[url] = "avatar fetching disabled"
            return None
        try:
            if self._avatar_fetcher is not None:
                data = self._avatar_fetcher(url)
            else:
                data = fetch_avatar_bytes(
                    url,
                    proxy_url=self.proxy_url,
                    timeout_seconds=self.timeout_seconds,
                    max_bytes=self.max_avatar_bytes,
                )
            if data is None:
                self._fetch_errors[url] = "fetcher returned no bytes"
                return None
            self.avatar_downloads += 1
            return bytes(data)
        except Exception as exc:  # noqa: BLE001 - a missing avatar is a non-match
            self._fetch_errors[url] = str(exc)[:300]
            return None

    def avatar_hashes(self, entity: Any) -> ImageHashes | None:
        parsed = self.prepare(entity)
        if parsed.avatar_phash:
            return ImageHashes(
                sha256="",
                ahash="",
                dhash="",
                phash=parsed.avatar_phash,
            )
        if parsed.avatar_bytes is not None:
            try:
                return hash_ensemble(parsed.avatar_bytes)
            except Exception as exc:  # noqa: BLE001
                self._fetch_errors[f"bytes:{id(entity)}"] = str(exc)[:300]
                return None
        if not parsed.avatar_url:
            return None
        if parsed.avatar_url in self._hash_cache:
            return self._hash_cache[parsed.avatar_url]
        data = self._fetch(parsed.avatar_url)
        if data is None:
            self._hash_cache[parsed.avatar_url] = None
            return None
        try:
            hashes = hash_ensemble(data)
        except Exception as exc:  # noqa: BLE001 - unsupported image is not a match
            self._fetch_errors[parsed.avatar_url] = str(exc)[:300]
            self._hash_cache[parsed.avatar_url] = None
            return None
        self._hash_cache[parsed.avatar_url] = hashes
        return hashes

    @staticmethod
    def network_overlap(
        left: ProfileAttributes, right: ProfileAttributes
    ) -> NetworkOverlap:
        jaccard = round(jaccard_similarity(left.connections, right.connections), 6)
        return NetworkOverlap(
            left=left.connections,
            right=right.connections,
            jaccard=jaccard,
            significant=bool(left.connections and right.connections)
            and jaccard >= NETWORK_JACCARD_THRESHOLD,
        )

    def link(self, left: Any, right: Any) -> list[ProfileLink]:
        """Return confirmed avatar/network links for one entity pair.

        Both signals can fire independently: an avatar match and a network
        overlap each produce their own ``SAME_AS_CONFIRMED`` edge so the
        evidence chain names the actual source.
        """
        left_profile = self.prepare(left)
        right_profile = self.prepare(right)
        links: list[ProfileLink] = []
        left_hashes = self.avatar_hashes(left)
        right_hashes = self.avatar_hashes(right)
        if left_hashes is not None and right_hashes is not None:
            try:
                distance = hamming_text(left_hashes.phash, right_hashes.phash)
            except ValueError:
                distance = 999
            if distance <= AVATAR_PHASH_MAX_DISTANCE:
                links.append(
                    ProfileLink(
                        left_entity_id=getattr(left, "entity_id"),
                        right_entity_id=getattr(right, "entity_id"),
                        relationship=RelationshipType.SAME_AS_CONFIRMED,
                        confidence=AVATAR_CONFIDENCE,
                        source="avatar_phash",
                        detail=(
                            "avatar pHash Hamming distance "
                            f"{distance} <= {AVATAR_PHASH_MAX_DISTANCE}"
                        ),
                        left_value=getattr(left, "canonical_value", left_profile.label),
                        right_value=getattr(right, "canonical_value", right_profile.label),
                        left_platform=left_profile.platform,
                        right_platform=right_profile.platform,
                        metrics={
                            "phash_distance": distance,
                            "max_distance": AVATAR_PHASH_MAX_DISTANCE,
                        },
                    )
                )
        network = self.network_overlap(left_profile, right_profile)
        if network.significant:
            links.append(
                ProfileLink(
                    left_entity_id=getattr(left, "entity_id"),
                    right_entity_id=getattr(right, "entity_id"),
                    relationship=RelationshipType.SAME_AS_CONFIRMED,
                    confidence=NETWORK_CONFIDENCE,
                    source="network_overlap",
                    detail=(
                        "network overlap Jaccard "
                        f"{network.jaccard:.6f} >= {NETWORK_JACCARD_THRESHOLD}"
                    ),
                    left_value=getattr(left, "canonical_value", left_profile.label),
                    right_value=getattr(right, "canonical_value", right_profile.label),
                    left_platform=left_profile.platform,
                    right_platform=right_profile.platform,
                    metrics=network.to_dict(),
                )
            )
        return links


def profile_temporal_cadence(
    left: ProfileAttributes,
    right: ProfileAttributes,
    *,
    threshold: float = TEMPORAL_OVERLAP_THRESHOLD,
) -> TemporalCadence:
    """Compare the two profiles' public-activity cadences."""
    return compare_activity_histograms(
        left.timestamp_values(),
        right.timestamp_values(),
        threshold=threshold,
    )


def profile_comparison_pairs(
    items: Sequence[tuple[UUID, Mapping[str, Any] | None]],
    *,
    max_profiles: int = PROFILE_PAIR_MAX_PROFILES,
    max_pairs: int = PROFILE_PAIR_MAX_PAIRS,
    include_ids: Iterable[UUID] | None = None,
) -> tuple[tuple[UUID, UUID], ...]:
    """Bounded profile-level block for the cascade engine.

    Phase 17 blocking intentionally uses strong keys only. Profile attributes
    (avatar pHash, connections, activity) have no shared strong key -- an
    avatar match can exist across different handles -- so Phase 18.1 adds one
    explicitly bounded profile block. It is not a general weak-key chain: only
    profile-shaped claims participate, and both profile count and pair count
    are capped. ``include_ids`` lets phase-2 callers add typed social-account
    entities that have not yet acquired profile attributes.
    """
    if max_profiles < 2 or max_pairs < 1:
        return ()
    included = set(include_ids or ())
    profiles: list[tuple[UUID, ProfileAttributes]] = []
    for entity_id, attributes in items:
        parsed = ProfileAttributes.from_attributes(attributes)
        if parsed.has_profile_data or entity_id in included:
            profiles.append((entity_id, parsed))
    profiles.sort(key=lambda pair: str(pair[0]))
    profiles = profiles[:max_profiles]
    pairs: list[tuple[UUID, UUID]] = []
    for (left_id, _), (right_id, _) in combinations(profiles, 2):
        pairs.append(
            (left_id, right_id) if str(left_id) <= str(right_id) else (right_id, left_id)
        )
        if len(pairs) >= max_pairs:
            break
    return tuple(sorted(set(pairs), key=lambda pair: (str(pair[0]), str(pair[1]))))


def profile_fuzzy_similarity(left: ProfileAttributes, right: ProfileAttributes) -> tuple[float, str]:
    """Best public-name similarity between two profiles.

    The returned value is the *base* similarity. Callers that also have a
    significant temporal cadence apply the documented ``+0.15`` boost to the
    resolver score; the base value is what the interactive review band sees so
    the operator label is not silently inflated.
    """
    candidates: list[tuple[float, str]] = []
    if left.username and right.username:
        candidates.append(
            (jaro_winkler(fold_diacritics(left.username), fold_diacritics(right.username)), "username")
        )
    if left.display_name and right.display_name:
        candidates.append(
            (
                jaro_winkler(
                    fold_diacritics(left.display_name), fold_diacritics(right.display_name)
                ),
                "display_name",
            )
        )
    if not candidates:
        return 0.0, ""
    return max(candidates, key=lambda item: item[0])
