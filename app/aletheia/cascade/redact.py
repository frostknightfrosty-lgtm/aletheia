"""Deterministic redaction for shareable artifacts (P17.8).

Design of record: ``docs/PIVOT_CASCADE.md`` section 11 — "reports can be
generated ``--redact``ed for sharing".

Redaction replaces person identifiers with deterministic tokens
(``redacted:<sha256-16 hex>``): the same value always maps to the same token,
so joins and structure survive sharing while the value itself is
unrecoverable from the artifact. Only the documented person-identifier types
are touched; platform names, adapter names, dates, and reasons stay readable.
These functions operate on this package's own artifact schemas (trail hops,
dossier fields and subject), never on arbitrary payloads.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from aletheia.core.models import EntityType, SeedType

__all__ = [
    "REDACTED_ENTITY_TYPES",
    "REDACTED_SEED_TYPES",
    "redact_dossier",
    "redact_token",
    "redact_trail",
]

REDACTED_SEED_TYPES = frozenset(
    {
        SeedType.EMAIL,
        SeedType.PHONE,
        SeedType.NAME,
        SeedType.PERSON_NAME,
        SeedType.GEOLOCATION,
    }
)

REDACTED_ENTITY_TYPES = frozenset(
    {
        EntityType.EMAIL,
        EntityType.PHONE,
        EntityType.NAME,
        EntityType.PERSON,
        EntityType.GEOLOCATION,
    }
)


def redact_token(value: str) -> str:
    """The deterministic share token for one identifier value."""
    return "redacted:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def redact_trail(trail: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of the trail with person-identifier seed values tokenized."""
    redacted = dict(trail)
    hops = []
    for hop in trail.get("hops", []):
        hop_copy = dict(hop)
        try:
            seed_type = SeedType(str(hop["seed_type"]))
        except (KeyError, ValueError):
            seed_type = None
        if seed_type in REDACTED_SEED_TYPES and isinstance(hop_copy.get("seed_value"), str):
            hop_copy["seed_value"] = redact_token(hop_copy["seed_value"])
        hops.append(hop_copy)
    redacted["hops"] = hops
    return redacted


def redact_dossier(dossier: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of the dossier with person-identifier values tokenized.

    Covers the subject seeds and every cluster field whose entity type is a
    person identifier; the evidence chains are kept (they carry kinds and
    sources, not values).
    """
    redacted = dict(dossier)
    subject = []
    for seed in dossier.get("subject", []):
        seed_copy = dict(seed)
        try:
            seed_type = SeedType(str(seed.get("type")))
        except ValueError:
            seed_type = None
        if seed_type in REDACTED_SEED_TYPES and isinstance(seed_copy.get("value"), str):
            seed_copy["value"] = redact_token(seed_copy["value"])
        subject.append(seed_copy)
    redacted["subject"] = subject
    clusters = []
    for cluster in dossier.get("clusters", []):
        cluster_copy = dict(cluster)
        fields = []
        for field in cluster.get("fields", []):
            field_copy = dict(field)
            try:
                entity_type = EntityType(str(field["entity_type"]))
            except (KeyError, ValueError):
                entity_type = None
            if entity_type in REDACTED_ENTITY_TYPES and isinstance(field_copy.get("value"), str):
                field_copy["value"] = redact_token(field_copy["value"])
            fields.append(field_copy)
        cluster_copy["fields"] = fields
        clusters.append(cluster_copy)
    redacted["clusters"] = clusters
    return redacted
