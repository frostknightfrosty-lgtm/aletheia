"""Coverage-invariant tests for the descriptor-derived routing graph (P17.2).

The graph is derived from the live adapter registry, so these tests walk the
same 49 descriptors production walks. Negative controls tamper with a copy of
the graph and prove the validator actually fails (the invariant is load
bearing, not decorative).
"""

from __future__ import annotations

import pytest

from aletheia.adapters.registry import phase7_adapters
from aletheia.cascade.routing import (
    BRIDGE_SEED_TYPES,
    TERMINAL_ENTITY_TYPES,
    TEXT_AUTODETECT_ENTITY_TYPES,
    RoutingCoverageError,
    RoutingGraph,
    build_routing_graph,
    validate_routing_graph,
)
from aletheia.core.models import AdapterDescriptor, EntityType, SeedType


class _StubAdapter:
    def __init__(self, name: str, inputs: list[SeedType], outputs: list[EntityType]) -> None:
        self.descriptor = AdapterDescriptor(
            name=name,
            license="test",
            input_types=inputs,
            output_types=outputs,
            legal_notes=[],
            rate_limit="n/a",
            invocation="test",
            version_pin="v1",
            upstream="https://example.invalid",
            network_required=False,
            docker_image="aletheia/test:v1",
        )


def _tampered(graph: RoutingGraph, **overrides) -> RoutingGraph:
    data = {
        "adapter_routes": dict(graph.adapter_routes),
        "adapter_outputs": dict(graph.adapter_outputs),
        "bridges": dict(graph.bridges),
        "terminal_entities": frozenset(graph.terminal_entities),
        "text_autodetect_entities": frozenset(graph.text_autodetect_entities),
    }
    data.update(overrides)
    return RoutingGraph(**data)


def test_routes_are_derived_from_descriptors_not_hardcoded():
    adapters = phase7_adapters()
    graph = build_routing_graph(adapters)
    assert set(graph.adapter_outputs) == set(adapters)
    for seed_type in SeedType:
        expected = tuple(
            sorted(name for name, adapter in adapters.items() if seed_type in adapter.descriptor.input_types)
        )
        assert graph.adapters_for_seed(seed_type) == expected


def test_build_routing_graph_defaults_to_the_live_registry():
    assert build_routing_graph().adapter_routes == build_routing_graph(phase7_adapters()).adapter_routes


def test_every_seed_type_has_at_least_one_route():
    graph = build_routing_graph()
    uncovered = [seed_type.value for seed_type in SeedType if not graph.adapters_for_seed(seed_type)]
    assert uncovered == []


def test_every_entity_type_is_bridged_terminal_or_autodetected():
    graph = build_routing_graph()
    unclassified = [
        entity_type.value for entity_type in EntityType if not graph.is_entity_classified(entity_type)
    ]
    assert unclassified == []


def test_every_adapter_output_is_classified():
    graph = build_routing_graph()
    problems = [
        f"{name}:{entity_type.value}"
        for name, outputs in graph.adapter_outputs.items()
        for entity_type in outputs
        if not graph.is_entity_classified(entity_type)
    ]
    assert problems == []


def test_bridge_classification_is_total_and_disjoint():
    classified = set(BRIDGE_SEED_TYPES) | set(TERMINAL_ENTITY_TYPES) | set(TEXT_AUTODETECT_ENTITY_TYPES)
    assert classified == set(EntityType)
    assert not set(BRIDGE_SEED_TYPES) & set(TERMINAL_ENTITY_TYPES)
    assert not set(BRIDGE_SEED_TYPES) & set(TEXT_AUTODETECT_ENTITY_TYPES)
    assert not set(TERMINAL_ENTITY_TYPES) & set(TEXT_AUTODETECT_ENTITY_TYPES)


def test_validate_routing_graph_passes_for_the_live_registry():
    validate_routing_graph(build_routing_graph())


def test_validate_rejects_missing_seed_route():
    graph = build_routing_graph()
    tampered = _tampered(graph, adapter_routes={**graph.adapter_routes, SeedType.USERNAME: ()})
    with pytest.raises(RoutingCoverageError) as excinfo:
        validate_routing_graph(tampered)
    assert "seed type 'username' has no adapter route" in str(excinfo.value)


def test_validate_rejects_unclassified_entity_type():
    graph = build_routing_graph()
    bridges = {key: value for key, value in graph.bridges.items() if key is not EntityType.LEI}
    tampered = _tampered(graph, bridges=bridges)
    with pytest.raises(RoutingCoverageError) as excinfo:
        validate_routing_graph(tampered)
    assert "entity type 'lei' is neither bridged" in str(excinfo.value)


def test_validate_rejects_dead_bridge():
    graph = build_routing_graph()
    tampered = _tampered(graph, adapter_routes={**graph.adapter_routes, SeedType.CRYPTO_ADDRESS: ()})
    with pytest.raises(RoutingCoverageError) as excinfo:
        validate_routing_graph(tampered)
    assert "bridge 'blockchain_intel_record' -> 'crypto_address' is dead" in str(excinfo.value)


def test_validate_rejects_unclassified_adapter_output():
    graph = build_routing_graph()
    outputs = {**graph.adapter_outputs, "sherlock": frozenset({EntityType.LEI})}
    bridges = {key: value for key, value in graph.bridges.items() if key is not EntityType.LEI}
    tampered = _tampered(graph, adapter_outputs=outputs, bridges=bridges)
    with pytest.raises(RoutingCoverageError) as excinfo:
        validate_routing_graph(tampered)
    assert "adapter 'sherlock' declares unclassified output 'lei'" in str(excinfo.value)


def test_build_routing_graph_uses_only_the_supplied_descriptors():
    stub = {"only": _StubAdapter("only", [SeedType.VIN], [EntityType.TRANSPORT_ASSET_RECORD])}
    graph = build_routing_graph(stub)
    assert graph.adapters_for_seed(SeedType.VIN) == ("only",)
    assert graph.adapters_for_seed(SeedType.USERNAME) == ()
    with pytest.raises(RoutingCoverageError):
        validate_routing_graph(graph)


def test_next_and_reachable_seed_types():
    graph = build_routing_graph()
    one_hop = graph.next_seed_types(SeedType.USERNAME)
    assert {SeedType.URL, SeedType.DOMAIN, SeedType.USERNAME} <= one_hop
    closure = graph.reachable_seed_types(SeedType.USERNAME)
    assert {SeedType.URL, SeedType.DOMAIN, SeedType.EMAIL} <= closure
    assert SeedType.USERNAME in closure  # loops back through handles


def test_text_autodetect_entities_bridge_to_every_seed_type():
    graph = build_routing_graph()
    assert graph.bridge_seed_types(EntityType.OCR_TEXT) == frozenset(SeedType)
    assert graph.bridge_seed_types(EntityType.SERVICE) == frozenset()
    assert graph.bridge_seed_types(EntityType.UNKNOWN) == frozenset()
