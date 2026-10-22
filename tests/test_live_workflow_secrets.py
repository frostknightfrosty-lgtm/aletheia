"""The live workflows are the only path that exercises keyed adapters.

A secret can be present in GitHub Actions and still be inert if the workflow
does not export it. These tests pin the current Gate 3 secret set to both live
workflow entry points.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ("live-investigation.yml", "live-cascade.yml")
REQUIRED_SECRETS = (
    "LEAKIX_API_KEY",
    "GRAYHATWARFARE_TOKEN",
    "IPGEOLOCATION_KEY",
    "ABUSEIPDB_KEY",
    "NETLAS_KEY",
    "SAUCENAO_API_KEY",
    "URLHAUS_AUTH_KEY",
    "THREATFOX_AUTH_KEY",
    "MALWAREBAZAAR_AUTH_KEY",
    "YOUTUBE_API_KEY",
)


def test_live_workflows_pass_configured_gate3_secrets():
    missing = []
    for workflow in WORKFLOWS:
        text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        for secret in REQUIRED_SECRETS:
            needle = secret + ": ${{ secrets." + secret + " }}"
            if needle not in text:
                missing.append(f"{workflow}: {secret}")
    assert not missing, "Live workflows do not export: " + ", ".join(missing)
