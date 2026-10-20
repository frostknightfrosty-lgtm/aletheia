import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


docker = shutil.which("docker")
pytestmark = pytest.mark.integration


def _run(args):
    if not docker:
        pytest.skip("Docker CLI unavailable in this environment")
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def test_sherlock_container_smoke():
    r = _run(["docker", "run", "--rm", "aletheia/sherlock:0.16.2", "--version"])
    assert r.returncode == 0
    assert "Sherlock" in r.stdout or "Sherlock" in r.stderr


def test_theharvester_container_smoke():
    r = _run(["docker", "run", "--rm", "aletheia/theharvester:4.11.1", "-h"])
    assert r.returncode == 0
    assert "theHarvester" in (r.stdout + r.stderr)


def test_exiftool_container_smoke(tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_text("Aletheia", encoding="utf-8")
    # Mount a read-only evidence file and request JSON metadata; no network is used.
    r = _run(["docker", "run", "--rm", "--network", "none", "-v", f"{sample}:/work/sample.txt:ro",
              "aletheia/exiftool:13.59", "-j", "/work/sample.txt"])
    assert r.returncode == 0
    assert '"SourceFile"' in r.stdout

@pytest.mark.parametrize("image,command", [
    ("aletheia/amass:5.1.1", ["-version"]),
    ("aletheia/subfinder:2.17.0", ["-version"]),
    ("aletheia/assetfinder:0.1.1", ["--help"]),
    ("aletheia/dnsx:1.3.1", ["-version"]),
    ("aletheia/massdns:1.1.0", ["--help"]),
    ("aletheia/dnsrecon:1.6.3", ["--help"]),
    ("aletheia/fierce:1.6.0", ["--help"]),
    ("aletheia/shodan:1.31.0", ["--health"]),
    ("aletheia/crtsh:public-json", ["--health"]),
])
def test_phase3_container_health_smoke(image, command):
    r = _run(["docker", "run", "--rm", "--network", "none", image, *command])
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("image,args", [
    ("aletheia/maigret:0.6.6", ["--version"]),
    ("aletheia/holehe:1.61", ["-c", "from holehe.core import __version__; print(__version__)"]),
    ("aletheia/h8mail:2.5.6", ["--help"]),
    ("aletheia/hibp:api-v3", ["--health"]),
    ("aletheia/xposedornot:api-v1", ["--health"]),
    ("aletheia/phoneinfoga:2.11.0", ["version"]),
    ("aletheia/libphonenumber:9.0.40", ["--health"]),
])
def test_phase4_docker_health(image, args):
    entrypoint = ["--entrypoint", "python"] if image == "aletheia/holehe:1.61" else []
    r = _run(["docker", "run", "--rm", "--network", "none", *entrypoint, image, *args])
    assert r.returncode == 0, r.stderr or r.stdout


def test_phase4_maigret_starts_with_a_read_only_root():
    """Every adapter container runs with --read-only; maigret's startup used to
    create ~/.maigret and crash with "Read-only file system" before checking a
    single site (live run 39125383530). --no-autoupdate keeps the pinned bundled
    database and never touches the home directory."""
    r = _run([
        "docker", "run", "--rm", "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "-w", "/tmp",
        "aletheia/maigret:0.6.6",
        "--no-autoupdate",
    ])
    assert r.returncode == 0, r.stderr or r.stdout
    assert "Read-only file system" not in (r.stdout + r.stderr)


@pytest.mark.parametrize("image,args", [
    ("aletheia/instaloader:4.15.3", ["--health"]),
    ("aletheia/reddit-api:v1", ["--health"]),
    ("aletheia/youtube-api:v3", ["--health"]),
    ("aletheia/overpass:public", ["--health"]),
    ("aletheia/suncalc:2.0.2", ["--health"]),
    ("aletheia/deepface:0.0.101", ["--health"]),
    ("aletheia/insightface:2.1", ["--health"]),
])
def test_phase5_docker_health(image,args):
    r=_run(["docker","run","--rm","--network","none",image,*args])
    assert r.returncode==0, r.stderr or r.stdout


@pytest.mark.parametrize("image,args", [
    ("aletheia/sec-edgar:public-api", ["--health"]),
    ("aletheia/gleif:api-v1", ["--health"]),
    ("aletheia/opencorporates:api-v0.4.8", ["--health"]),
    ("aletheia/opensanctions:api", ["--health"]),
    ("aletheia/courtlistener:api-v3", ["--health"]),
])
def test_phase6_docker_health(image,args):
    r=_run(["docker","run","--rm","--network","none",image,*args])
    assert r.returncode==0, r.stderr or r.stdout


def test_phase7_core_image_imports():
    r=_run(["docker","run","--rm","--network","none","--entrypoint","python","aletheia/core:0.7.0","-c","import aletheia; print('core import ok')"])
    assert r.returncode==0, r.stderr or r.stdout


def test_phase5c_gravatar_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/gravatar:api-v3", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout


def test_phase5c_rdap_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/rdap:rfc9082", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout


def test_phase9_ip_intelligence_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/ip-intelligence:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout


def test_phase9_gov_records_us_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/gov-records-us:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_corp_registry_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/corp-registry:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_sanctions_watchlists_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/sanctions-watchlists:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_academic_search_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/academic-search:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_ssl_tls_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/ssl-tls:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_crypto_blockchain_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/crypto-blockchain:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_patents_trademarks_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/patents-trademarks:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_email_auth_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/email-auth:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_code_search_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/code-search:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_search_engines_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/search-engines:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_geolocation_image_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/geolocation-image:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_transport_asset_registry_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/transport-asset-registry:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_social_profile_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/social-profile:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_social_username_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/social-username:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase9_leak_checkers_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/leak-checkers:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase17_zehef_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/zehef:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase17_tiktok_hashtag_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/tiktok-hashtag:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase17_venom_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/venom:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase17_picimagesearch_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/picimagesearch:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase17_tracelines_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/tracelines:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase17_shadowfinder_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/shadowfinder:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase17_pybdshadow_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/pybdshadow:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase17_crypttrace_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/crypttrace:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_phase11_egress_proxy_container_health():
    r = _run(["docker", "run", "--rm", "--network", "none", "aletheia/egress-proxy:v1", "--health"])
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


# -- Phase 12: proxied path, adapter egress, and fail-closed -------------------
#
# The whole wiring scenario runs once per test session through ci/egress_scenario.py
# (real Docker, a custom --internal network, a local origin, and the adapter image);
# the individual tests below assert their slice of the shared summary.

_SCENARIO: dict = {}


def _scenario_summary() -> dict:
    if "summary" not in _SCENARIO:
        if not docker:
            pytest.skip("Docker CLI unavailable in this environment")
        repo_root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable, "ci/egress_scenario.py", "--json"],
            cwd=repo_root, capture_output=True, text=True, timeout=900,
        )
        lines = [line for line in proc.stdout.splitlines() if line.strip().startswith("{")]
        _SCENARIO["summary"] = json.loads(lines[-1]) if lines else {"checks": []}
        _SCENARIO["stderr"] = proc.stderr
    return _SCENARIO["summary"]


def _scenario_check(name: str) -> dict:
    summary = _scenario_summary()
    checks = {check["name"]: check for check in summary.get("checks", [])}
    assert name in checks, f"scenario did not report {name!r}: {summary} ({_SCENARIO.get('stderr', '')})"
    return checks[name]


def test_phase12_egress_proxied_path():
    forward = _scenario_check("phase12-egress-forward")
    assert forward["ok"], forward["detail"]
    chain_check = _scenario_check("phase12-egress-chain")
    assert chain_check["ok"], chain_check["detail"]


def test_phase12_egress_adapter_proxied():
    check = _scenario_check("phase12-egress-adapter-proxied")
    assert check["ok"], check["detail"]


def test_phase12_egress_fail_closed():
    check = _scenario_check("phase12-egress-fail-closed")
    assert check["ok"], check["detail"]


def test_phase12_egress_uplink_forward():
    """The proxy's second interface is its only route to any upstream (repair
    after run 39120709419: a single-homed proxy can reach nothing)."""
    check = _scenario_check("phase12-egress-uplink-forward")
    assert check["ok"], check["detail"]


def test_phase12_egress_uplink_is_isolated():
    """Adapters on the internal network must not reach the uplink directly."""
    check = _scenario_check("phase12-egress-uplink-isolated")
    assert check["ok"], check["detail"]


def test_phase12_egress_uplink_https():
    """The CONNECT tunnel must relay both directions: TLS only completes when
    the client's handshake bytes reach the upstream while its reply comes back
    (repair after run 39125383530: every CONNECT entry logged bytes=0 and every
    adapter's HTTPS request failed with SSL errors)."""
    check = _scenario_check("phase12-egress-uplink-https")
    assert check["ok"], check["detail"]


# -- Phase 15: wiring coverage is a policy, not an allowlist -------------------


def test_phase15_egress_policy_covers_every_network_adapter():
    check = _scenario_check("phase15-egress-policy-covers-registry")
    assert check["ok"], check["detail"]


def test_phase15_egress_previously_unwired_adapter_is_proxied():
    check = _scenario_check("phase15-egress-previously-unwired-adapter")
    assert check["ok"], check["detail"]
