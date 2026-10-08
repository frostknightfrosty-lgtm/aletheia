from aletheia.adapters.registry import phase1_adapters
from aletheia.core.models import AdapterRunRequest, Seed, SeedType
from uuid import uuid4


def test_commands_are_docker_safe_contracts(tmp_path):
    cases = [
        ("sherlock", SeedType.USERNAME, "alice"),
        ("theHarvester", SeedType.DOMAIN, "example.com"),
    ]
    adapters = phase1_adapters()
    for name, kind, value in cases:
        cmd = adapters[name].build_command(AdapterRunRequest(run_id=uuid4(), seed=Seed(type=kind, value=value)), tmp_path / name)
        assert cmd
        assert "--proxy" not in cmd  # transport is injected by Aletheia, not passed as seed data
