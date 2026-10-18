"""Tiered dossier artifact (P17.8).

Design of record: ``docs/PIVOT_CASCADE.md`` section 12 — ``dossier.json``
("tiered identity, evidence chain per field").

Inputs are explicit and evidence is never invented: a field whose evidence
chain is empty is serialized with ``supported: false`` rather than dropped or
fabricated. Clusters sort by tier (confirmed, probable, possible, excluded,
then unreviewed) and id; fields sort by ``(entity_type, value)``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from aletheia.core.models import EntityType, IdentityTier, Seed

__all__ = ["DossierCluster", "DossierField", "EvidenceRef", "build_dossier"]


@dataclass(frozen=True)
class EvidenceRef:
    """One link in a field's evidence chain."""

    kind: str
    source: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "source": self.source, "note": self.note}


@dataclass(frozen=True)
class DossierField:
    entity_type: EntityType
    value: str
    evidence: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class DossierCluster:
    cluster_id: str
    tier: IdentityTier | None
    fields: tuple[DossierField, ...] = ()


_TIER_ORDER = {
    IdentityTier.CONFIRMED: 0,
    IdentityTier.PROBABLE: 1,
    IdentityTier.POSSIBLE: 2,
    IdentityTier.EXCLUDED: 3,
    None: 4,
}


def build_dossier(
    *,
    subject_seeds: Sequence[Seed],
    clusters: Sequence[DossierCluster],
    run_id: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Validate and serialize the tiered dossier, deterministically."""
    if not subject_seeds:
        raise ValueError("a dossier needs at least one subject seed")
    cluster_ids = [cluster.cluster_id for cluster in clusters]
    if any(not cluster_id for cluster_id in cluster_ids):
        raise ValueError("cluster_id must be non-empty")
    if len(set(cluster_ids)) != len(cluster_ids):
        raise ValueError("duplicate cluster_id")
    for cluster in clusters:
        if cluster.tier is not None and not isinstance(cluster.tier, IdentityTier):
            raise ValueError(f"cluster {cluster.cluster_id}: unknown tier {cluster.tier!r}")
    ordered = sorted(clusters, key=lambda cluster: (_TIER_ORDER[cluster.tier], cluster.cluster_id))
    payload_clusters = []
    for cluster in ordered:
        fields = sorted(cluster.fields, key=lambda field: (field.entity_type.value, field.value))
        payload_clusters.append(
            {
                "cluster_id": cluster.cluster_id,
                "tier": cluster.tier.value if cluster.tier is not None else None,
                "fields": [
                    {
                        "entity_type": field.entity_type.value,
                        "value": field.value,
                        "evidence": [ref.to_dict() for ref in field.evidence],
                        "supported": len(field.evidence) > 0,
                    }
                    for field in fields
                ],
            }
        )
    return {
        "dossier_version": 1,
        "run_id": run_id,
        "case_id": case_id,
        "subject": [seed.model_dump(mode="json") for seed in subject_seeds],
        "clusters": payload_clusters,
    }
