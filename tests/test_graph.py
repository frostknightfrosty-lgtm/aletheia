from aletheia.core.graph import Graph
from aletheia.core.models import EntityType, Finding, Provenance


def test_graph_deduplicates_entity_values():
    g = Graph()
    p = Provenance(tool="test", confidence=0.9, adapter_version="1")
    g.ingest(Finding(entity_type=EntityType.URL, value="https://x", provenance=p))
    g.ingest(Finding(entity_type=EntityType.URL, value="https://x", provenance=p))
    urls = [e for e in g.entities.values() if e.canonical_value == "https://x"]
    assert len(urls) == 1
    assert len(g.edges) == 2
