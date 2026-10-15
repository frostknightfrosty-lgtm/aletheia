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
    assert len(manifest["pending"]) == 13
    assert "rdap" in manifest["pending"]
    assert "opensanctions" in manifest["pending"]
    assert "ssl_tls" in manifest["pending"]
    assert set(manifest["pending"]) == {
        "theHarvester", "amass", "subfinder", "assetfinder", "dnsx", "massdns",
        "dnsrecon", "fierce", "shodan", "crt.sh", "opensanctions", "rdap", "ssl_tls",
    }
