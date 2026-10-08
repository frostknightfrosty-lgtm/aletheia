from aletheia.adapters.registry import phase1_adapters


def test_phase1_inventory_is_exact():
    adapters = phase1_adapters()
    assert set(adapters) == {"sherlock", "theHarvester", "exiftool"}
    assert adapters["theHarvester"].descriptor.license == "GPL-2.0-only"
