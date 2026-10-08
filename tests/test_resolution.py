from aletheia.core.graph import Graph
from aletheia.core.models import EntityType
from aletheia.phase2.resolution import EntityResolver, normalize_value


def test_normalization_is_type_aware():
    assert normalize_value(EntityType.USERNAME, " @Alice ").canonical == "alice"
    assert normalize_value(EntityType.DOMAIN, "Example.COM.").canonical == "example.com"
    assert normalize_value(EntityType.URL, "HTTPS://Example.COM:443/a/#frag").canonical == "https://example.com/a"


def test_exact_canonical_values_merge_and_preserve_alias():
    g = Graph()
    a = g.upsert_entity(EntityType.DOMAIN, "Example.COM.")
    b = g.upsert_entity(EntityType.DOMAIN, "example.com")
    assert a.entity_id != b.entity_id
    candidates = EntityResolver().resolve(g)
    assert candidates == []
    assert len(g.entities) == 1
    merged = next(iter(g.entities.values()))
    assert "example.com" in {merged.canonical_value, *merged.attributes.get("aliases", [])}
    assert "Example.COM." in merged.attributes.get("aliases", [])


def test_fuzzy_similarity_becomes_candidate_not_fact():
    g = Graph()
    a = g.upsert_entity(EntityType.USERNAME, "alice")
    b = g.upsert_entity(EntityType.USERNAME, "alica")
    candidates = EntityResolver(candidate_threshold=0.75).resolve(g)
    assert len(candidates) == 1
    assert candidates[0].decision == "candidate"
    assert a.entity_id in g.entities and b.entity_id in g.entities
    assert any(e.relationship.value == "same_as_candidate" for e in g.edges.values())


def test_phone_normalization_preserves_e164_digits_only():
    from aletheia.phase2.resolution import normalize_value
    from aletheia.core.models import EntityType
    normalized = normalize_value(EntityType.PHONE, "+1 (415) 555-2671")
    assert normalized.canonical == "+14155552671"


def test_geolocation_normalization_rounds_decimal_coordinates():
    from aletheia.phase2.resolution import normalize_value
    out = normalize_value(EntityType.GEOLOCATION, " 51.5000009, -0.1000004 ")
    assert out.canonical == "51.500001,-0.100000"


def test_image_normalization_preserves_path():
    from aletheia.phase2.resolution import normalize_value
    out = normalize_value(EntityType.IMAGE, "/tmp/photo.JPG")
    assert out.canonical == "/tmp/photo.JPG"
