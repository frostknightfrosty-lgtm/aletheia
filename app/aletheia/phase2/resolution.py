from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from rapidfuzz.distance import JaroWinkler, Levenshtein

from aletheia.core.calibration import Calibrator
from aletheia.core.graph import Graph
from aletheia.core.models import Entity, EntityType, RelationshipType, Provenance


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


class EntityResolver:
    """Conservative, explainable resolver.

    Exact canonical matches are merged. Fuzzy matches are never silently merged;
    they become explicit SAME_AS_CANDIDATE edges with a machine-readable explanation.
    """

    def __init__(self, *, candidate_threshold: float = 0.88, auto_merge_threshold: float = 0.985,
                 calibrator: Calibrator | None = None) -> None:
        self.candidate_threshold = candidate_threshold
        self.auto_merge_threshold = auto_merge_threshold
        # A calibrator maps the raw similarity score to a probability. When it is
        # absent or untrained, candidates are reported as ``calibrated: false``.
        self.calibrator = calibrator

    def resolve(self, graph: Graph) -> list[ResolutionCandidate]:
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
                        jw, lev, score = _score(left.canonical_value, right.canonical_value)
                        if score < self.candidate_threshold:
                            continue
                        decision = "candidate"
                        explanation = [
                            f"same_entity_type={entity_type.value}",
                            f"jaro_winkler={jw:.6f}",
                            f"levenshtein={lev:.6f}",
                            "no automatic merge because fuzzy similarity is not source evidence",
                        ]
                        calibrated = self.calibrator is not None and self.calibrator.trained
                        probability = (
                            round(self.calibrator.predict(score), 6)
                            if calibrated and self.calibrator is not None
                            else None
                        )
                        if calibrated:
                            explanation.append("calibrated=true")
                            explanation.append(f"calibrated_probability={probability:.6f}")
                        else:
                            explanation.append("calibrated=false")
                            explanation.append("no_trained_calibrator_score_is_similarity_not_probability")
                        if score >= self.auto_merge_threshold:
                            # Still require exact canonical equality for merge; threshold alone cannot authorize it.
                            explanation.append("auto_merge_blocked_by_policy_exact_match_only")
                        candidates.append(ResolutionCandidate(
                            left.entity_id, right.entity_id, entity_type,
                            left.canonical_value, right.canonical_value,
                            jw, lev, score, decision, tuple(explanation),
                            calibrated, probability,
                        ))
                        graph.link(left, right, RelationshipType.SAME_AS_CANDIDATE, score, provenance,
                                   attributes={"resolution": candidates[-1].to_dict()})
        return candidates
