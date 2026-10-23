"""Descriptor-derived routing graph for the pivot cascade (Phase 17, P17.2).

Design of record: ``docs/PIVOT_CASCADE.md`` sections 4 and 4.1. The graph is
built from the live adapter registry — every route is a fact of an adapter's
``input_types`` / ``output_types`` descriptor, never a hardcoded list. The
bridge map below is the extractor-side classification the design requires:
every ``EntityType`` must resolve to at least one bridge (an entity class that
can become a seed again — the class-jumping mechanism) or an explicit terminal
classification. The extractors that produce the typed values land with P17.3
and must implement exactly this mapping.

``validate_routing_graph`` enforces the build-time invariants:

1. every ``SeedType`` member has at least one adapter route;
2. every ``EntityType`` member is bridged, terminal, or text-autodetected;
3. every ``EntityType`` any adapter declares as output is classified, so no
   finding can land in a dead end;
4. every bridge target is itself routable (no dead bridges).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from aletheia.core.adapters import Adapter
from aletheia.core.models import EntityType, SeedType

__all__ = [
    "BRIDGE_SEED_TYPES",
    "TERMINAL_ENTITY_TYPES",
    "TEXT_AUTODETECT_ENTITY_TYPES",
    "RoutingCoverageError",
    "RoutingGraph",
    "build_routing_graph",
    "validate_routing_graph",
]

# EntityType -> the seed types an extractor may derive from a claim of that
# type (design section 4.1, "bridge claims"). These are reviewable structural
# constants; the runtime gates of design section 7 (cluster tier) decide
# whether a specific pivot is actually taken.
BRIDGE_SEED_TYPES: dict[EntityType, frozenset[SeedType]] = {
    EntityType.PERSON: frozenset({SeedType.NAME, SeedType.PERSON_NAME}),
    EntityType.USERNAME: frozenset({SeedType.USERNAME}),
    EntityType.NAME: frozenset({SeedType.NAME, SeedType.PERSON_NAME}),
    EntityType.DOMAIN: frozenset({SeedType.DOMAIN, SeedType.URL}),
    EntityType.URL: frozenset({SeedType.URL, SeedType.DOMAIN}),
    EntityType.EMAIL: frozenset({SeedType.EMAIL, SeedType.DOMAIN}),
    EntityType.IP: frozenset({SeedType.IP, SeedType.DOMAIN}),
    EntityType.HOST: frozenset({SeedType.DOMAIN, SeedType.IP}),
    EntityType.FILE: frozenset({SeedType.FILE_PATH}),
    EntityType.PHONE: frozenset({SeedType.PHONE}),
    EntityType.BREACH: frozenset({SeedType.DOMAIN, SeedType.EMAIL}),
    EntityType.SOCIAL_ACCOUNT: frozenset({SeedType.URL, SeedType.USERNAME}),
    EntityType.PLACE: frozenset({SeedType.GEOLOCATION}),
    EntityType.GEOLOCATION: frozenset({SeedType.GEOLOCATION}),
    EntityType.IMAGE: frozenset({SeedType.IMAGE, SeedType.FILE_PATH}),
    EntityType.COMPANY: frozenset({SeedType.COMPANY_NAME}),
    EntityType.LEGAL_ENTITY: frozenset({SeedType.COMPANY_NAME}),
    EntityType.LEI: frozenset({SeedType.COMPANY_NAME}),
    EntityType.FILING: frozenset({SeedType.COMPANY_NAME, SeedType.PERSON_NAME, SeedType.NAME}),
    EntityType.COURT_CASE: frozenset({SeedType.PERSON_NAME, SeedType.COMPANY_NAME, SeedType.NAME}),
    EntityType.SANCTION: frozenset({SeedType.PERSON_NAME, SeedType.COMPANY_NAME, SeedType.NAME}),
    EntityType.GOVERNMENT_RECORD: frozenset(
        {SeedType.PERSON_NAME, SeedType.COMPANY_NAME, SeedType.NAME}
    ),
    EntityType.COMPANY_REGISTRY_RECORD: frozenset(
        {SeedType.COMPANY_NAME, SeedType.PERSON_NAME, SeedType.NAME}
    ),
    EntityType.ACADEMIC_RECORD: frozenset({SeedType.PERSON_NAME}),
    EntityType.TLS_OBSERVATION: frozenset({SeedType.DOMAIN, SeedType.IP}),
    EntityType.BLOCKCHAIN_INTEL_RECORD: frozenset({SeedType.CRYPTO_ADDRESS, SeedType.URL}),
    EntityType.INTELLECTUAL_PROPERTY_RECORD: frozenset(
        {SeedType.PERSON_NAME, SeedType.COMPANY_NAME, SeedType.NAME}
    ),
    EntityType.EMAIL_AUTH_RECORD: frozenset({SeedType.DOMAIN}),
    EntityType.TECHNICAL_FINDING: frozenset(
        {SeedType.EMAIL, SeedType.URL, SeedType.DOMAIN, SeedType.USERNAME}
    ),
    EntityType.WEB_SEARCH_RESULT: frozenset({SeedType.URL, SeedType.DOMAIN}),
    EntityType.GEO_EVIDENCE: frozenset({SeedType.GEOLOCATION}),
    EntityType.TRANSPORT_ASSET_RECORD: frozenset({SeedType.VIN, SeedType.NAME}),
}

# Observations that deliberately never spawn a new search by themselves.
TERMINAL_ENTITY_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.SERVICE,  # an account-exists / exposure observation on a service
        EntityType.BREACH_HIT,  # a leak-index hit, not a search target by itself
        EntityType.FACE,  # compared locally (pHash); never a seed
        EntityType.JURISDICTION,  # a context-filter hint, not a query
        EntityType.UNKNOWN,  # catch-all
    }
)

# Text-bearing entities whose value is re-parsed by seed autodetection
# (:func:`aletheia.cascade.seeds.detect_seeds`). OCR output can contain any
# seed class, so these bridge to "whatever the detector finds" rather than a
# fixed list.
TEXT_AUTODETECT_ENTITY_TYPES: frozenset[EntityType] = frozenset({EntityType.OCR_TEXT})


class RoutingCoverageError(ValueError):
    """Raised when the routing graph violates a build-time coverage invariant."""


@dataclass(frozen=True)
class RoutingGraph:
    """The cascade's runtime graph: SeedType -> adapters -> EntityType -> seeds.

    ``adapter_routes`` maps every seed type to the (sorted, stable) names of
    the registered adapters that accept it. ``adapter_outputs`` is the reverse
    per-adapter descriptor view. The bridge fields carry the classifier
    constants above so consumers and validators share one source of truth.
    """

    adapter_routes: Mapping[SeedType, tuple[str, ...]]
    adapter_outputs: Mapping[str, frozenset[EntityType]]
    bridges: Mapping[EntityType, frozenset[SeedType]]
    terminal_entities: frozenset[EntityType]
    text_autodetect_entities: frozenset[EntityType]

    def adapters_for_seed(self, seed_type: SeedType) -> tuple[str, ...]:
        return self.adapter_routes.get(seed_type, ())

    def bridge_seed_types(self, entity_type: EntityType) -> frozenset[SeedType]:
        """Seed types an observed claim of ``entity_type`` can become.

        Text-autodetected entities can yield any seed type the detector knows;
        terminal entities and unclassified entity types yield nothing.
        """
        if entity_type in self.text_autodetect_entities:
            return frozenset(SeedType)
        return self.bridges.get(entity_type, frozenset())

    def is_entity_classified(self, entity_type: EntityType) -> bool:
        return (
            entity_type in self.bridges
            or entity_type in self.terminal_entities
            or entity_type in self.text_autodetect_entities
        )

    def next_seed_types(self, seed_type: SeedType) -> frozenset[SeedType]:
        """Seed types reachable from ``seed_type`` in exactly one pivot hop."""
        reachable: set[SeedType] = set()
        for adapter_name in self.adapters_for_seed(seed_type):
            for entity_type in self.adapter_outputs.get(adapter_name, frozenset()):
                reachable.update(self.bridge_seed_types(entity_type))
        return frozenset(reachable)

    def reachable_seed_types(self, seed_type: SeedType) -> frozenset[SeedType]:
        """Transitive closure of :meth:`next_seed_types`.

        The start appears in the result only when a cycle returns to it (for
        example handle -> social account -> new handle), which is the honest
        reading of "reachable".
        """
        seen: set[SeedType] = set()
        frontier = [seed_type]
        while frontier:
            current = frontier.pop()
            for candidate in self.next_seed_types(current):
                if candidate not in seen:
                    seen.add(candidate)
                    frontier.append(candidate)
        return frozenset(seen)


def build_routing_graph(adapters: Mapping[str, Adapter] | None = None) -> RoutingGraph:
    """Derive the routing graph from adapter descriptors.

    ``adapters`` defaults to the live Phase 7 registry, so production and the
    coverage tests walk exactly the same descriptors.
    """
    if adapters is None:
        from aletheia.adapters.registry import phase7_adapters

        adapters = phase7_adapters()
    routes: dict[SeedType, list[str]] = {seed_type: [] for seed_type in SeedType}
    outputs: dict[str, frozenset[EntityType]] = {}
    for name, adapter in adapters.items():
        descriptor = adapter.descriptor
        for seed_type in descriptor.input_types:
            routes[seed_type].append(name)
        outputs[name] = frozenset(descriptor.output_types)
    return RoutingGraph(
        adapter_routes={seed_type: tuple(sorted(names)) for seed_type, names in routes.items()},
        adapter_outputs=outputs,
        bridges=BRIDGE_SEED_TYPES,
        terminal_entities=TERMINAL_ENTITY_TYPES,
        text_autodetect_entities=TEXT_AUTODETECT_ENTITY_TYPES,
    )


def validate_routing_graph(graph: RoutingGraph) -> None:
    """Raise :class:`RoutingCoverageError` listing every coverage violation."""
    problems: list[str] = []
    for seed_type in SeedType:
        if not graph.adapters_for_seed(seed_type):
            problems.append(f"seed type {seed_type.value!r} has no adapter route")
    for entity_type in EntityType:
        if not graph.is_entity_classified(entity_type):
            problems.append(
                f"entity type {entity_type.value!r} is neither bridged, terminal, nor text-autodetected"
            )
    for adapter_name, entity_types in sorted(graph.adapter_outputs.items()):
        for entity_type in entity_types:
            if not graph.is_entity_classified(entity_type):
                problems.append(
                    f"adapter {adapter_name!r} declares unclassified output {entity_type.value!r}"
                )
    for entity_type, targets in sorted(graph.bridges.items(), key=lambda item: item[0].value):
        for seed_type in sorted(targets, key=lambda item: item.value):
            if not graph.adapters_for_seed(seed_type):
                problems.append(
                    f"bridge {entity_type.value!r} -> {seed_type.value!r} is dead: no adapter route"
                )
    if problems:
        raise RoutingCoverageError("routing coverage violations: " + "; ".join(sorted(set(problems))))
