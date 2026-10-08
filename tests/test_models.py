from aletheia.core.models import Seed, SeedType, Finding, EntityType, Provenance


def test_seed_and_finding_are_typed():
    seed = Seed(type=SeedType.USERNAME, value=" alice ")
    assert seed.value == "alice"
    finding = Finding(entity_type=EntityType.URL, value="https://example.test/u/alice",
                      provenance=Provenance(tool="sherlock", confidence=0.8, adapter_version="0.16.2"))
    assert finding.provenance.confidence == 0.8


def test_new_phase6_seed_types():
    from aletheia.core.models import Seed
    assert Seed(type="name", value="Acme Corp").type.value == "name"
