from pathlib import Path
import json

from aletheia.core.models import Seed, SeedType
from aletheia.core.orchestrator import Orchestrator


def test_domain_run_manifest_contains_phase3_and_authorization(tmp_path):
    orch = Orchestrator(tmp_path)
    run_id = orch.create_run(
        Seed(type=SeedType.DOMAIN, value="example.com"),
        legal_only=True,
        authorization_assertion="Authorized test scope",
    )
    manifest = orch.checkpoints.load(run_id)
    assert manifest is not None
    assert manifest["goal"].startswith("Aletheia investigation")
    assert manifest["authorization_assertion"] == "Authorized test scope"
    # Derived from the live adapter registry instead of a hardcoded list, so adding a
    # DOMAIN-capable adapter no longer requires editing this test. The assertion is stronger
    # than the old literal set: the run manifest must list exactly the registered adapters
    # whose descriptor accepts a DOMAIN seed, so a wrong or stale pending list still fails.
    from aletheia.adapters.registry import phase7_adapters

    domain_capable = {
        name
        for name, adapter in phase7_adapters().items()
        if SeedType.DOMAIN in adapter.descriptor.input_types
    }
    assert domain_capable, "expected at least one DOMAIN-capable adapter in the registry"
    assert set(manifest["pending"]) == domain_capable
    # Named spot-checks keep the intent of this test readable.
    assert {"rdap", "opensanctions", "ssl_tls", "email_auth"} <= set(manifest["pending"])
