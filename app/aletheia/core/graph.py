from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aletheia.core.models import Edge, Entity, Finding, RelationshipType


def _priority(attributes: dict) -> str:
    value = str(attributes.get("source_priority", "primary")).strip().lower()
    return value if value in {"primary", "secondary"} else "primary"


def _merge_attributes(target: dict, incoming: dict | None) -> None:
    """Merge attributes without letting a secondary source overwrite native data.

    A native observation (``primary``) always wins a key conflict. A secondary
    observation can still fill keys the primary source did not supply, which is
    how a SpiderFoot batch run reinforces an existing cluster without replacing
    the adapter-of-record value.
    """
    if not incoming:
        return
    target_priority = _priority(target)
    incoming_priority = _priority(incoming)
    if target_priority == "primary" and incoming_priority == "secondary":
        for key, value in incoming.items():
            if key == "source_priority":
                continue
            target.setdefault(key, value)
        target["source_priority"] = "primary"
        return
    if target_priority == "secondary" and incoming_priority == "primary":
        target.update(incoming)
        target["source_priority"] = "primary"
        return
    target.update(incoming)
    target["source_priority"] = incoming_priority


@dataclass
class Graph:
    entities: dict[UUID, Entity] = field(default_factory=dict)
    edges: dict[UUID, Edge] = field(default_factory=dict)
    by_key: dict[tuple[str, str], UUID] = field(default_factory=dict)

    def upsert_entity(self, entity_type: str, canonical_value: str, attributes: dict | None = None) -> Entity:
        # Accept enums or their serialized string representation.
        entity_type_value = getattr(entity_type, "value", entity_type)
        key = (entity_type_value, canonical_value)
        incoming = dict(attributes or {})
        incoming.setdefault("source_priority", "primary")
        existing_id = self.by_key.get(key)
        if existing_id:
            entity = self.entities[existing_id]
            _merge_attributes(entity.attributes, incoming)
            return entity
        entity = Entity(entity_type=entity_type_value, canonical_value=canonical_value, attributes=incoming)
        self.entities[entity.entity_id] = entity
        self.by_key[key] = entity.entity_id
        return entity

    def ingest(self, finding: Finding) -> tuple[Entity, Edge]:
        attributes = dict(finding.attributes)
        attributes["source_priority"] = finding.source_priority
        target = self.upsert_entity(finding.entity_type, finding.value, attributes)
        seed_entity = self.upsert_entity("unknown", f"finding:{finding.finding_id}", {"source_kind": finding.source_kind})
        edge = Edge(
            source_entity_id=seed_entity.entity_id,
            target_entity_id=target.entity_id,
            relationship=RelationshipType.DERIVED_FROM,
            confidence=finding.provenance.confidence,
            provenance=finding.provenance,
            attributes={"finding_id": str(finding.finding_id)},
        )
        self.edges[edge.edge_id] = edge
        return target, edge

    def link(self, source: Entity, target: Entity, relationship: RelationshipType, confidence: float, provenance,
             attributes: dict | None = None) -> Edge:
        edge = Edge(source_entity_id=source.entity_id, target_entity_id=target.entity_id,
                    relationship=relationship, confidence=confidence, provenance=provenance,
                    attributes=attributes or {})
        self.edges[edge.edge_id] = edge
        return edge

    def merge_entities(self, keep_id: UUID, drop_id: UUID, *, reason: str) -> Entity:
        if keep_id == drop_id:
            return self.entities[keep_id]
        keep = self.entities[keep_id]
        drop = self.entities[drop_id]
        _merge_attributes(keep.attributes, drop.attributes)
        aliases = keep.attributes.setdefault("aliases", [])
        if drop.canonical_value != keep.canonical_value and drop.canonical_value not in aliases:
            aliases.append(drop.canonical_value)
        merged = keep.attributes.setdefault("merged_entities", [])
        if str(drop.entity_id) not in merged:
            merged.append(str(drop.entity_id))
        keep.attributes.setdefault("merge_reasons", []).append(reason)
        keep.first_seen = min(keep.first_seen, drop.first_seen)
        keep.last_seen = max(keep.last_seen, drop.last_seen)

        for edge in self.edges.values():
            if edge.source_entity_id == drop_id:
                edge.source_entity_id = keep_id
            if edge.target_entity_id == drop_id:
                edge.target_entity_id = keep_id
        for key, value in list(self.by_key.items()):
            if value == drop_id:
                self.by_key[key] = keep_id
        del self.entities[drop_id]
        return keep

    @classmethod
    def from_export(cls, payload: dict) -> "Graph":
        graph = cls()
        for raw in payload.get("entities", []):
            entity = Entity.model_validate(raw)
            graph.entities[entity.entity_id] = entity
            graph.by_key[(entity.entity_type.value, entity.canonical_value)] = entity.entity_id
        for raw in payload.get("edges", []):
            edge = Edge.model_validate(raw)
            graph.edges[edge.edge_id] = edge
        return graph

    def export(self) -> dict:
        return {"entities": [e.model_dump(mode="json") for e in self.entities.values()],
                "edges": [e.model_dump(mode="json") for e in self.edges.values()]}
