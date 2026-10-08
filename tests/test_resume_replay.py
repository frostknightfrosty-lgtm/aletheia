import json
from aletheia.core.graph import Graph
from aletheia.core.models import EntityType


def test_graph_replays_from_persisted_export():
    g = Graph()
    e = g.upsert_entity(EntityType.URL, "https://example.test")
    payload = g.export()
    g2 = Graph.from_export(json.loads(json.dumps(payload)))
    assert any(x.canonical_value == "https://example.test" for x in g2.entities.values())
    assert g2.by_key[("url", "https://example.test")] == e.entity_id
