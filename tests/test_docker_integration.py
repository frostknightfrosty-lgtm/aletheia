import shutil
import subprocess
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
