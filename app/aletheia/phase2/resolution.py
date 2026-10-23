from __future__ import annotations

import ipaddress
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from rapidfuzz.distance import JaroWinkler, Levenshtein

from aletheia.cascade.profile_linking import (
    AvatarFetcher,
    ProfileAttributes,
    ProfileEnricher,
    ProfileLink,
    ProfileLinker,
    profile_comparison_pairs,
    profile_temporal_cadence,
)
from aletheia.cascade.scoring import TEMPORAL_CONFIDENCE_BOOST
from aletheia.core.calibration import Calibrator
from aletheia.core.graph import Graph
from aletheia.core.models import ContextFilters, Entity, EntityType, RelationshipType, Provenance


@dataclass(frozen=True)
class NormalizedValue:
    entity_type: EntityType
    original: str
    canonical: str
    rules: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionCandidate:
    left_entity_id: UUID
    right_entity_id: UUID
    entity_type: EntityType
    left_value: str
    right_value: str
    jaro_winkler: float
    levenshtein: float
    score: float
    decision: str
    explanation: tuple[str, ...]
    # Phase 13: the composite ``score`` is a similarity heuristic. ``calibrated``
    # is True only when a trained calibrator produced ``calibrated_probability``.
    calibrated: bool = False
    calibrated_probability: float | None = None
    # Phase 18.1: public-activity cadence support for a fuzzy match.
    temporal_overlap: float | None = None
    temporal_boost: float = 0.0

    def to_dict(self) -> dict:
        raw = asdict(self)
        raw["left_entity_id"] = str(self.left_entity_id)
        raw["right_entity_id"] = str(self.right_entity_id)
        raw["entity_type"] = self.entity_type.value
        return raw


def normalize_value(entity_type: EntityType, value: str) -> NormalizedValue:
    original = value
    value = value.strip()
    rules: list[str] = ["trim_whitespace"]

    if entity_type == EntityType.USERNAME:
        if value.startswith("@"):  # common presentation-only prefix
            value = value[1:]
            rules.append("remove_leading_at")
        canonical = value.casefold()
        if canonical != value:
            rules.append("casefold")
        return NormalizedValue(entity_type, original, canonical, tuple(rules))

    if entity_type in {EntityType.DOMAIN, EntityType.HOST}:
        value = value.rstrip(".")
        if value != original.strip():
            rules.append("remove_trailing_dot")
        canonical = value.casefold()
        if canonical != value:
            rules.append("casefold")
        return NormalizedValue(entity_type, original, canonical, tuple(rules))

    if entity_type == EntityType.EMAIL:
        canonical = value.casefold()
        if canonical != value:
            rules.append("casefold")
        return NormalizedValue(entity_type, original, canonical, tuple(rules))

    if entity_type == EntityType.PHONE:
        # Canonicalize presentation differences without inferring country or subscriber identity.
        compact = re.sub(r"[\s().-]+", "", value)
        if compact.startswith("00"):
            compact = "+" + compact[2:]
            rules.append("convert_international_00_prefix")
        if compact.startswith("+"):
            canonical = "+" + re.sub(r"\D", "", compact[1:])
        else:
            canonical = re.sub(r"\D", "", compact)
            rules.append("strip_non_digits")
        return NormalizedValue(entity_type, original, canonical, tuple(rules))

    if entity_type in {EntityType.IP}:
        try:
            canonical = str(ipaddress.ip_address(value))
            if canonical != value:
                rules.append("ip_address_canonicalization")
        except ValueError:
            canonical = value.casefold()
            rules.append("invalid_ip_fallback_casefold")
        return NormalizedValue(entity_type, original, canonical, tuple(rules))

    if entity_type == EntityType.URL:
        parsed = urlsplit(value)
        if parsed.scheme and parsed.netloc:
            scheme = parsed.scheme.casefold()
            hostname = (parsed.hostname or "").casefold()
            userinfo = ""
            if parsed.username:
                userinfo = parsed.username
                if parsed.password is not None:
                    userinfo += ":" + parsed.password
                userinfo += "@"
            port = ""
            try:
                parsed_port = parsed.port
            except ValueError:
                parsed_port = None
                rules.append("invalid_port_preserved")
            default_port = (scheme == "http" and parsed_port == 80) or (scheme == "https" and parsed_port == 443)
            if parsed_port is not None and not default_port:
                port = f":{parsed_port}"
            netloc = f"{userinfo}{hostname}{port}"
            path = parsed.path or "/"
            if path != "/" and path.endswith("/"):
                path = path.rstrip("/") or "/"
                rules.append("remove_trailing_path_slash")
            if parsed.fragment:
                rules.append("remove_fragment")
            canonical = urlunsplit((scheme, netloc, path, parsed.query, ""))
            if canonical != value:
                rules.append("url_component_canonicalization")
            return NormalizedValue(entity_type, original, canonical, tuple(rules))
        return NormalizedValue(entity_type, original, value.casefold(), tuple(rules + ["casefold_fallback"]))

    if entity_type in {EntityType.FILE, EntityType.IMAGE}:
        # Do not resolve symlinks or touch the file here; identity is path-based.
        canonical = value
        rules.append("path_preserved")
        return NormalizedValue(entity_type, original, canonical, tuple(rules))

    if entity_type == EntityType.GEOLOCATION:
        parts = [part.strip() for part in value.split(",")]
        if len(parts) >= 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    canonical = f"{lat:.6f},{lon:.6f}"
                    rules.append("coordinate_decimal_canonicalization")
                    return NormalizedValue(entity_type, original, canonical, tuple(rules))
            except ValueError:
                pass
        canonical = re.sub(r"\s+", " ", value).casefold()
        rules.append("invalid_geolocation_fallback")
        return NormalizedValue(entity_type, original, canonical, tuple(rules))

    canonical = re.sub(r"\s+", " ", value).casefold()
    if canonical != value:
        rules.extend(["collapse_whitespace", "casefold"])
    return NormalizedValue(entity_type, original, canonical, tuple(rules))


def _score(left: str, right: str) -> tuple[float, float, float]:
    jw = JaroWinkler.normalized_similarity(left, right)
    lev = Levenshtein.normalized_similarity(left, right)
    # Favor Jaro-Winkler for short human-facing identifiers while retaining edit-distance evidence.
    composite = round((0.65 * jw) + (0.35 * lev), 6)
    return round(jw, 6), round(lev, 6), composite


def _is_secondary(entity: Entity) -> bool:
    return str(entity.attributes.get("source_priority", "primary")).strip().lower() == "secondary"


def seed_attribution(graph: Graph) -> dict[UUID, set[int]]:
    """Map each entity to the seed-tree indexes its evidence came from.

    ``Graph.ingest`` points a DERIVED_FROM edge from a per-finding node at the
    observed entity and ``merge_entities`` redirects those edges to the kept
    entity, so edge provenance is the durable record of which seed expansion
    produced the evidence. The resolver's own SAME_AS_CANDIDATE edges carry no
    seed index and are ignored. Single-seed runs leave the index unset, so they
    yield an empty attribution and behave exactly as before.
    """
    attribution: dict[UUID, set[int]] = {}
    for edge in graph.edges.values():
        seed_index = edge.provenance.seed_index
        if seed_index is None:
            continue
        attribution.setdefault(edge.target_entity_id, set()).add(seed_index)
    return attribution


_COUNTRY_ATTRS = ("country", "country_code", "address_country", "jurisdiction")
_LANGUAGE_ATTRS = ("language", "languages", "lang")
_TIMEZONE_ATTRS = ("timezone", "time_zone", "tz")
_AGE_ATTRS = ("age",)
_BIRTH_YEAR_ATTRS = ("birth_year",)
_BIRTHDATE_ATTRS = ("birthdate", "birth_date", "dob")


def _attr_values(entity: Entity, keys: tuple[str, ...]) -> list[str]:
    lowered = {str(key).casefold(): value for key, value in entity.attributes.items()}
    values: list[str] = []
    for key in keys:
        value = lowered.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return values


def _token_match(filter_value: str, attr_value: str) -> bool:
    """Case-insensitive token match; a longer filter may also match as substring."""
    needle = filter_value.casefold().strip()
    haystack = attr_value.casefold().strip()
    if not needle or not haystack:
        return False
    tokens = {token for token in re.split(r"[^a-z0-9]+", haystack) if token}
    if needle in tokens:
        return True
    return len(needle) > 3 and needle in haystack


def _substring_match(filter_value: str, attr_value: str) -> bool:
    needle = filter_value.casefold().strip()
    haystack = attr_value.casefold().strip()
    if not needle or not haystack:
        return False
    return needle in haystack or haystack in needle


def _compute_age(entity: Entity) -> int | None:
    lowered = {str(key).casefold(): value for key, value in entity.attributes.items()}
    for key in _AGE_ATTRS:
        try:
            age = int(lowered[key])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= age <= 130:
            return age
    today = datetime.now(timezone.utc).date()
    for key in _BIRTH_YEAR_ATTRS:
        try:
            birth_year = int(lowered[key])
        except (KeyError, TypeError, ValueError):
            continue
        if 1900 <= birth_year <= today.year:
            return today.year - birth_year
    for key in _BIRTHDATE_ATTRS:
        raw = lowered.get(key)
        if not isinstance(raw, str):
            continue
        try:
            parsed = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        age = today.year - parsed.year - ((today.month, today.day) < (parsed.month, parsed.day))
        if 0 <= age <= 130:
            return age
    return None


def _filter_mismatch(entity: Entity, filters: ContextFilters | None) -> str | None:
    """Return a human-readable mismatch, or ``None`` when the entity is compatible.

    Only positive mismatches count: an entity that records nothing for a
    filtered attribute cannot be excluded by that filter.
    """
    if filters is None or filters.is_empty():
        return None
    if filters.country:
        values = _attr_values(entity, _COUNTRY_ATTRS)
        if values and not any(_token_match(filters.country, value) for value in values):
            return f"country filter '{filters.country}' does not match recorded {values}"
    if filters.language:
        values = _attr_values(entity, _LANGUAGE_ATTRS)
        if values and not any(_token_match(filters.language, value) for value in values):
            return f"language filter '{filters.language}' does not match recorded {values}"
    if filters.timezone:
        values = _attr_values(entity, _TIMEZONE_ATTRS)
        if values and not any(_substring_match(filters.timezone, value) for value in values):
            return f"timezone filter '{filters.timezone}' does not match recorded {values}"
    if filters.age_min is not None or filters.age_max is not None:
        age = _compute_age(entity)
        if age is not None:
            if filters.age_min is not None and age < filters.age_min:
                return f"computed age {age} is below age_min {filters.age_min}"
            if filters.age_max is not None and age > filters.age_max:
                return f"computed age {age} is above age_max {filters.age_max}"
    return None


class EntityResolver:
    """Conservative, explainable resolver.

    Exact canonical matches are merged. Fuzzy matches are never silently merged;
    they become explicit SAME_AS_CANDIDATE edges with a machine-readable explanation.
    """

    def __init__(
        self,
        *,
        candidate_threshold: float = 0.88,
        auto_merge_threshold: float = 0.985,
        calibrator: Calibrator | None = None,
        avatar_fetcher: AvatarFetcher | None = None,
        profile_enricher: ProfileEnricher | None = None,
        proxy_url: str | None = None,
        fetch_avatars: bool = True,
    ) -> None:
        self.candidate_threshold = candidate_threshold
        self.auto_merge_threshold = auto_merge_threshold
        # A calibrator maps the raw similarity score to a probability. When it is
        # absent or untrained, candidates are reported as ``calibrated: false``.
        self.calibrator = calibrator
        # Phase 18.1 profile linking. The fetcher/enricher are injected so tests
        # (and offline runs) never touch the network; the default fetcher is the
        # proxy-aware public-image path. An adapter that omitted the avatar is
        # asked for it through ``profile_enricher`` before the pair is compared.
        self.profile_linker = ProfileLinker(
            avatar_fetcher=avatar_fetcher,
            profile_enricher=profile_enricher,
            proxy_url=proxy_url,
            fetch_avatars=fetch_avatars,
        )
        self.last_confirmed_links: list[ProfileLink] = []

    def resolve(self, graph: Graph, *, context_filters: ContextFilters | None = None) -> list[ResolutionCandidate]:
        self.last_confirmed_links = []
        # First pass: canonicalize and exact-merge within an entity type.
        by_canonical: dict[tuple[EntityType, str], Entity] = {}
        candidates: list[ResolutionCandidate] = []
        entity_ids = list(graph.entities.keys())
        for entity_id in entity_ids:
            if entity_id not in graph.entities:
                continue
            entity = graph.entities[entity_id]
            normalized = normalize_value(entity.entity_type, entity.canonical_value)
            entity.attributes.setdefault("normalization", {})
            entity.attributes["normalization"] = {
                "canonical": normalized.canonical,
                "rules": list(normalized.rules),
            }
            key = (entity.entity_type, normalized.canonical)
            existing = by_canonical.get(key)
            if existing is None:
                by_canonical[key] = entity
                if entity.canonical_value != normalized.canonical:
                    entity.attributes.setdefault("aliases", []).append(entity.canonical_value)
                    entity.canonical_value = normalized.canonical
                continue
            if existing.entity_id == entity.entity_id:
                continue
            graph.merge_entities(existing.entity_id, entity.entity_id, reason="exact_canonical_match")

        # Second pass: fuzzy candidate generation over surviving entities of same type.
        # Seed-tree attribution is read after the exact merges so shared evidence
        # survives on the kept entity.
        attribution = seed_attribution(graph)
        survivors = list(graph.entities.values())
        grouped: dict[EntityType, list[Entity]] = {}
        for entity in survivors:
            grouped.setdefault(entity.entity_type, []).append(entity)
        provenance = Provenance(
            tool="aletheia.entity_resolver",
            source_url="internal://entity-resolution",
            observed_at=datetime.now(timezone.utc),
            confidence=1.0,
            adapter_version="0.2.0",
            notes=["Candidate similarity is analytic output, not source evidence."],
        )
        for entity_type, members in grouped.items():
            # Avoid O(n^2) explosions on very large groups by using a conservative blocking key.
            blocks: dict[str, list[Entity]] = {}
            for entity in members:
                value = entity.canonical_value.casefold()
                block = value[:3]
                if len(value) < 3:
                    block = value
                blocks.setdefault(block, []).append(entity)
            for block_members in blocks.values():
                if len(block_members) > 500:
                    block_members = block_members[:500]
                for i in range(len(block_members)):
                    for j in range(i + 1, len(block_members)):
                        left, right = block_members[i], block_members[j]
                        if _is_secondary(left) and _is_secondary(right):
                            # Two meta-adapter observations can corroborate a
                            # native cluster, but cannot create a new fuzzy
                            # cluster on their own.
                            continue
                        jw, lev, raw_score = _score(left.canonical_value, right.canonical_value)
                        score = raw_score
                        decision = "candidate"
                        explanation = [
                            f"same_entity_type={entity_type.value}",
                            f"jaro_winkler={jw:.6f}",
                            f"levenshtein={lev:.6f}",
                            "no automatic merge because fuzzy similarity is not source evidence",
                        ]
                        # Phase 18.1 temporal cadence: public post/comment
                        # timestamps produce 24 hourly bins; a significant
                        # overlap adds the documented +0.15 confidence boost.
                        # The boost is applied before the threshold check so a
                        # well-supported cadence can promote a borderline fuzzy
                        # match, but a single shared timestamp cannot.
                        left_profile = ProfileAttributes.from_attributes(left.attributes)
                        right_profile = ProfileAttributes.from_attributes(right.attributes)
                        cadence = profile_temporal_cadence(left_profile, right_profile)
                        temporal_overlap = cadence.overlap if cadence.left_samples or cadence.right_samples else None
                        temporal_boost = 0.0
                        if cadence.significant:
                            temporal_boost = TEMPORAL_CONFIDENCE_BOOST
                            score = min(1.0, round(score + temporal_boost, 6))
                            explanation.append(
                                f"temporal_active_hours_overlap={cadence.overlap:.6f}"
                            )
                            explanation.append(
                                f"temporal_boost={raw_score:.6f}->{score:.6f}"
                            )
                        if score < self.candidate_threshold:
                            continue
                        # Intersection pass: an entity corroborated by more than one
                        # seed tree gets a documented, bounded score boost. The boost
                        # never creates a candidate (the threshold was applied first)
                        # and never feeds the calibrator, which was trained on raw
                        # similarity scores.
                        trees = sorted(
                            attribution.get(left.entity_id, set()) | attribution.get(right.entity_id, set())
                        )
                        if len(trees) >= 2:
                            before_cross_seed = score
                            score = min(1.0, round(score * (1 + 0.05 * (len(trees) - 1)), 6))
                            explanation.append("cross_seed_trees=" + ",".join(str(index) for index in trees))
                            explanation.append(
                                f"cross_seed_boost={before_cross_seed:.6f}->{score:.6f}"
                            )
                            explanation.append(
                                "boost is a documented heuristic prior (5% per additional tree), not calibrator output"
                            )
                        calibrated = self.calibrator is not None and self.calibrator.trained
                        probability = (
                            round(self.calibrator.predict(raw_score), 6)
                            if calibrated and self.calibrator is not None
                            else None
                        )
                        if calibrated:
                            explanation.append("calibrated=true")
                            explanation.append(f"calibrated_probability={probability:.6f}")
                        else:
                            explanation.append("calibrated=false")
                            explanation.append("no_trained_calibrator_score_is_similarity_not_probability")
                        if raw_score >= self.auto_merge_threshold:
                            # Still require exact canonical equality for merge; threshold alone cannot authorize it.
                            explanation.append("auto_merge_blocked_by_policy_exact_match_only")
                        if context_filters is not None and not context_filters.is_empty():
                            mismatch = _filter_mismatch(left, context_filters) or _filter_mismatch(right, context_filters)
                            if mismatch:
                                decision = "filtered_out"
                                explanation.append(f"context_filter_mismatch={mismatch}")
                            else:
                                explanation.append("context_filters=no_conflict")
                        candidates.append(ResolutionCandidate(
                            left.entity_id, right.entity_id, entity_type,
                            left.canonical_value, right.canonical_value,
                            jw, lev, score, decision, tuple(explanation),
                            calibrated, probability, temporal_overlap, temporal_boost,
                        ))
                        graph.link(left, right, RelationshipType.SAME_AS_CANDIDATE, score, provenance,
                                   attributes={"resolution": candidates[-1].to_dict()})
        self._confirm_profile_links(graph, survivors)
        return candidates

    def _confirm_profile_links(self, graph: Graph, survivors: list[Entity]) -> None:
        """Inject Phase 18.1 SAME_AS_CONFIRMED profile edges.

        The profile block is separate from the type-specific fuzzy block because
        avatar/network evidence is cross-type by design (a GitHub social account
        and a Reddit URL can be the same person). Edges are idempotent per
        source/pair, and every edge carries the signal that produced it.
        """
        by_id = {entity.entity_id: entity for entity in survivors}
        # Ask the adapter-backed hook for a missing avatar before pair
        # generation. This is deliberately a pre-pass: a profile with no avatar
        # still gets the refetch attempt even when its only possible match has
        # already been discarded by the fuzzy pass.
        for entity in survivors:
            self.profile_linker.prepare(entity)
        include_ids = {
            entity.entity_id
            for entity in survivors
            if entity.entity_type is EntityType.SOCIAL_ACCOUNT
        }
        pairs = profile_comparison_pairs(
            [(entity.entity_id, entity.attributes) for entity in survivors],
            include_ids=include_ids,
        )
        existing: set[tuple[frozenset[UUID], str]] = set()
        for edge in graph.edges.values():
            if edge.relationship is not RelationshipType.SAME_AS_CONFIRMED:
                continue
            source = str(edge.attributes.get("source") or "")
            existing.add(
                (
                    frozenset({edge.source_entity_id, edge.target_entity_id}),
                    source,
                )
            )
        for left_id, right_id in pairs:
            left = by_id.get(left_id)
            right = by_id.get(right_id)
            if left is None or right is None:
                continue
            if _is_secondary(left) and _is_secondary(right):
                continue
            for link in self.profile_linker.link(left, right):
                key = (frozenset({left_id, right_id}), link.source)
                if key in existing:
                    continue
                provenance = Provenance(
                    tool="aletheia.profile_linker",
                    source_url="internal://phase18.1-profile-linking",
                    observed_at=datetime.now(timezone.utc),
                    confidence=link.confidence,
                    adapter_version="0.1.0",
                    notes=[
                        "Phase 18.1 profile-level link; avatar download, when used, "
                        "went through the configured egress proxy."
                    ],
                )
                graph.link(
                    left,
                    right,
                    RelationshipType.SAME_AS_CONFIRMED,
                    link.confidence,
                    provenance,
                    attributes=link.to_dict(),
                )
                self.last_confirmed_links.append(link)
                existing.add(key)
