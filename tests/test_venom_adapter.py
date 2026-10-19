"""Fixture/parser and driver tests for the venom adapter.

The parser test runs on ``tests/fixtures/venom.json`` — a synthetic document in
the exact shape the pinned driver prints (see ``docker/venom``). Driver checks
import the driver file directly; nothing here needs the upstream checkout or
network access.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path
from uuid import uuid4

import pytest

from parser_test_marker import parser_test

from aletheia.adapters.identity import VenomAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "venom.json"


def _request(seed_type=SeedType.USERNAME, value="example_user"):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=seed_type, value=value))


def _load_driver():
    path = ROOT / "docker" / "venom" / "run_venom.py"
    spec = importlib.util.spec_from_file_location("venom_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _by_type(findings):
    grouped = {}
    for finding in findings:
        grouped.setdefault(finding.entity_type, []).append(finding)
    return grouped


@parser_test("venom")
def test_venom_fixture_username_signals():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = VenomAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert json.loads(stdout)["pinned_commit"] in VenomAdapter.descriptor.version_pin
    grouped = _by_type(result.findings)
    assert len(result.findings) == 18
    assert len(grouped[EntityType.SOCIAL_ACCOUNT]) == 13
    assert len(grouped[EntityType.EMAIL]) == 3
    assert len(grouped[EntityType.URL]) == 1
    assert len(grouped[EntityType.BREACH]) == 1
    assert sorted(f.value for f in grouped[EntityType.EMAIL]) == [
        "dev@example.com", "npm@example.com", "user@example.com",
    ]
    mastodon = next(
        f for f in grouped[EntityType.SOCIAL_ACCOUNT] if f.attributes.get("platform") == "mastodon"
    )
    assert mastodon.value == "mastodon:example_user"
    assert mastodon.attributes["profile_url"] == "https://mastodon.social/@example_user"
    github = next(
        f for f in grouped[EntityType.SOCIAL_ACCOUNT] if f.attributes.get("source") == "venom-github"
    )
    assert github.attributes["followers"] == 42
    assert github.attributes["public_repos"] == 7
    assert github.attributes["recent_repos"] == ["alpha", "beta"]
    proofs = [
        f for f in grouped[EntityType.SOCIAL_ACCOUNT] if f.attributes.get("kind") == "keybase_proof"
    ]
    assert sorted(f.value for f in proofs) == ["github:example_user", "twitter:example_user"]
    paste = grouped[EntityType.BREACH][0]
    assert paste.value == "PSBDMP:abcd1234"
    assert paste.attributes == {
        "source": "psbdmp",
        "record_type": "paste_index_hit",
        "target": "example_user",
        "url": "https://pastebin.com/abcd1234",
        "paste_time": "2019-05-01T00:00:00Z",
        "index_count": 2,
    }
    assert "not downloaded" in paste.provenance.notes[0]
    assert "social sweep: 2 found / 1 not found / 0 inconclusive" in result.stderr_tail


def test_venom_parser_domain_assessments_skips_and_errors():
    stdout = json.dumps({
        "status": "ok",
        "target_type": "domain",
        "modules": {
            "dns": {"provider": "google", "a": ["203.0.113.10"], "mx": [], "ns": ["ns1.example-dns.org"], "txt": ["v=spf1 -all"]},
            "whois": {"registrar": "Example Registrar", "created": "2011-01-01"},
            "ip": {
                "ip": "203.0.113.10",
                "hostname": "host.example.com",
                "geo": {"org": "Example Networks", "city": "Berlin", "country": "DE"},
            },
            "wayback": {"first_snapshot": "2001-02-03"},
            "crt_subs": {
                "subdomains": [
                    {"subdomain": "www.example.com", "issued": "2024-01-01", "issuer": "Example CA"},
                    {"subdomain": "mail.example.com"},
                ]
            },
            "urlscan": {
                "results": [
                    {"url": "https://example.com/login", "scan_id": "aa-bb", "ip": "203.0.113.11",
                     "server": "nginx", "country": "de", "score": 0, "tags": ["login-page"]}
                ]
            },
            "otx_domain": {"count": 1, "pulses": [{"name": "example pulse"}]},
            "ht_dns": {"results": [{"hostname": "example.com", "ip": "203.0.113.10"}]},
            "ht_rev": {"status": "skipped", "reason": "the domain did not resolve to an address"},
            "pulsedive": {},
            "proxycheck": {"status": "ProxyCheck API Support"},
            "internetdb": {"ports": [80, 443], "hostnames": ["example.com"], "vulns": [], "tags": [], "cpes": []},
            "otx_ip": {"Status": "Protected by WAF", "details": "cloudflare"},
        },
    })
    result = VenomAdapter().parse(_request(SeedType.DOMAIN, "example.com"), Path("."), stdout, "", 0)
    grouped = _by_type(result.findings)
    assert len(result.findings) == 18
    assert sorted(f.value for f in grouped[EntityType.IP]) == [
        "203.0.113.10", "203.0.113.10", "203.0.113.11",
    ]
    assert sorted(f.value for f in grouped[EntityType.DOMAIN]) == [
        "example.com", "example.com", "host.example.com", "mail.example.com", "www.example.com",
    ]
    assert [f.value for f in grouped[EntityType.URL]] == ["https://example.com/login"]
    assert sorted(f.value for f in grouped[EntityType.UNKNOWN]) == [
        "venom:dns", "venom:ht_rev:skipped", "venom:internetdb", "venom:otx_domain",
        "venom:otx_ip:error", "venom:proxycheck", "venom:pulsedive:empty", "venom:wayback",
        "venom:whois",
    ]
    skipped = next(f for f in grouped[EntityType.UNKNOWN] if f.value == "venom:ht_rev:skipped")
    assert skipped.attributes["reason"] == "the domain did not resolve to an address"
    blocked = next(f for f in grouped[EntityType.UNKNOWN] if f.value == "venom:otx_ip:error")
    assert blocked.attributes["status"] == "blocked"
    assert blocked.attributes["detail"] == "Protected by WAF: cloudflare"
    whois = next(f for f in grouped[EntityType.UNKNOWN] if f.value == "venom:whois")
    assert whois.attributes["assessment"] == "domain registry (RDAP) summary"
    assert whois.attributes["registrar"] == "Example Registrar"
    assert "context, not a verdict" in whois.provenance.notes[0]
    assert "ht_rev: skipped" in result.stderr_tail


def test_venom_parser_email_signals_and_run_status_markers():
    stdout = json.dumps({
        "status": "ok",
        "target_type": "email",
        "modules": {
            "emailrep": {"_rate_limited": True},
            "crtsh_email": {
                "domains": [
                    {"domain": "user@example.com", "issued": "2020-01-01", "issuer": "Example CA"},
                    {"domain": "example.com"},
                ]
            },
            "psbdmp": {"count": 0, "pastes": []},
            "otx_email": {"count": 0, "results": []},
            "github_commits": {
                "commits": [
                    {"url": "https://github.com/example/repo/commit/abc123", "repo": "example/repo",
                     "date": "2018-01-01", "message": "fix typo"}
                ]
            },
        },
    })
    result = VenomAdapter().parse(_request(SeedType.EMAIL, "user@example.com"), Path("."), stdout, "", 0)
    grouped = _by_type(result.findings)
    assert [f.value for f in grouped[EntityType.EMAIL]] == ["user@example.com"]
    assert [f.value for f in grouped[EntityType.DOMAIN]] == ["example.com"]
    commit = grouped[EntityType.URL][0]
    assert commit.value == "https://github.com/example/repo/commit/abc123"
    assert commit.attributes["repo"] == "example/repo"
    assert commit.attributes["message_excerpt"] == "fix typo"
    assert sorted(f.value for f in grouped[EntityType.UNKNOWN]) == [
        "venom:emailrep:rate_limited", "venom:otx_email",
    ]
    rate_limited = next(
        f for f in grouped[EntityType.UNKNOWN] if f.value == "venom:emailrep:rate_limited"
    )
    assert "not retried" in rate_limited.provenance.notes[0]

    invalid = json.dumps({
        "status": "invalid_target", "target_type": "email",
        "error": "expected an email address", "modules": {},
    })
    result = VenomAdapter().parse(_request(SeedType.EMAIL, "user@example.com"), Path("."), invalid, "", 2)
    assert [f.value for f in result.findings] == ["venom:run:invalid_target"]
    assert result.findings[0].attributes["status"] == "invalid_target"
    assert result.findings[0].attributes["error"] == "expected an email address"
    assert result.status == "partial"

    blocked = json.dumps({"status": "blocked", "target_type": "email", "modules": {}})
    result = VenomAdapter().parse(_request(SeedType.EMAIL, "user@example.com"), Path("."), blocked, "", 0)
    assert [f.value for f in result.findings] == ["venom:run:blocked"]


def test_venom_parser_ignores_unparsable_payloads():
    result = VenomAdapter().parse(_request(), Path("."), "not-json", "", 1)
    assert result.findings == []
    assert result.status == "partial"


def test_venom_descriptor_is_registered_and_keyless():
    from aletheia.adapters.registry import phase7_adapters

    adapter = phase7_adapters()["venom"]
    descriptor = adapter.descriptor
    assert descriptor.input_types == [SeedType.EMAIL, SeedType.USERNAME, SeedType.DOMAIN]
    assert descriptor.output_types == [
        EntityType.SOCIAL_ACCOUNT, EntityType.URL, EntityType.EMAIL,
        EntityType.DOMAIN, EntityType.IP, EntityType.BREACH, EntityType.UNKNOWN,
    ]
    assert descriptor.docker_image == "aletheia/venom:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == []
    assert descriptor.parser_test_exempt is False
    assert "6fa3a483abc9cb0a1d96567e33b2919be59522c6" in descriptor.version_pin


def test_venom_build_command_maps_seed_types():
    adapter = VenomAdapter()
    assert adapter.build_command(_request(SeedType.EMAIL, "user@example.com"), None) == [
        "--type", "email", "user@example.com",
    ]
    assert adapter.build_command(_request(SeedType.USERNAME, "example_user"), None) == [
        "--type", "username", "example_user",
    ]
    assert adapter.build_command(_request(SeedType.DOMAIN, "example.com"), None) == [
        "--type", "domain", "example.com",
    ]
    with pytest.raises(ValueError):
        adapter.build_command(_request(SeedType.HASHTAG, "osint"), None)


# -- driver -------------------------------------------------------------------


def test_driver_target_validation():
    driver = _load_driver()
    assert driver._validate_target("email", " user@example.com ") == "user@example.com"
    assert driver._validate_target("email", "not-an-email") is None
    assert driver._validate_target("username", "example_user") == "example_user"
    assert driver._validate_target("username", "two words") is None
    assert driver._validate_target("domain", "Example.COM") == "example.com"
    assert driver._validate_target("domain", "no-dot") is None
    assert driver._validate_target("phone", "+15550100") is None


def test_driver_status_derivation():
    driver = _load_driver()
    assert driver._derive_status({}) == "error"
    assert driver._derive_status({"a": {"Status": "Protected by WAF"}}) == "blocked"
    assert driver._derive_status({"a": {"Status": "Timeout"}, "b": {"error": "boom"}}) == "error"
    assert driver._derive_status({"a": {"Status": "Timeout"}, "b": {"found": True}}) == "ok"


def test_driver_module_scoping_matches_the_review():
    driver = _load_driver()
    assert driver.EXPECTED_MODULE_BINDINGS == 30
    assert driver.EXPECTED_DISTINCT_CLASSES == 29
    assert [len(driver.MODULE_KEYS[key]) for key in ("email", "username", "domain")] == [5, 12, 13]
    assert "hibp_breaches" in driver.EXCLUDED_KEYS
    assert "leak_lookup" in driver.EXCLUDED_KEYS
    assert "dehashed" in driver.EXCLUDED_KEYS
    assert "holehe" in driver.EXCLUDED_KEYS
    assert "ipgeo" in driver.EXCLUDED_KEYS
    all_keys = [key for group in driver.MODULE_KEYS.values() for key in group]
    assert len(all_keys) == driver.EXPECTED_MODULE_BINDINGS
    assert not (set(all_keys) & set(driver.EXCLUDED_KEYS))


def test_driver_ua_patch_replaces_and_verifies():
    driver = _load_driver()

    class FakeModule:
        def get_random_user_agent(self):
            return "Mozilla/5.0 rotating"

    module = FakeModule()
    assert driver._apply_ua_patch([module]) is True
    assert module.get_random_user_agent() == driver.HONEST_UA
    assert driver._apply_ua_patch([]) is True


def test_driver_selftest_passes_with_stubs(tmp_path):
    driver = _load_driver()
    driver.CHECKOUT = str(tmp_path)
    (tmp_path / "PINNED_COMMIT").write_text(driver.PINNED_COMMIT, encoding="utf-8")
    shared = object()
    classes = {}
    for key in (key for group in driver.MODULE_KEYS.values() for key in group):
        classes[key] = shared if key in ("psbdmp", "psbdmp_u") else object()
    assert len(classes) == 30
    assert len(set(classes.values())) == 29
    report = driver.selftest(loader=lambda: classes, patcher=lambda: True, session_probe=lambda: True)
    assert report["venom_selftest"] == "ok"
    assert [check["name"] for check in report["checks"]] == [
        "pin_file", "module_imports", "ua_patch", "tls_verified",
        "target_validation", "module_scoping", "excluded_scope",
    ]
    assert all(check["ok"] for check in report["checks"])
    assert report["module_bindings"] == 30


def test_driver_selftest_reports_a_missing_checkout(tmp_path):
    driver = _load_driver()
    driver.CHECKOUT = str(tmp_path)
    (tmp_path / "PINNED_COMMIT").write_text(driver.PINNED_COMMIT, encoding="utf-8")

    def loader():
        raise RuntimeError("no checkout")

    report = driver.selftest(loader=loader, patcher=lambda: True, session_probe=lambda: True)
    assert report["venom_selftest"] == "fail"
    import_check = next(check for check in report["checks"] if check["name"] == "module_imports")
    assert import_check["ok"] is False
    assert "no checkout" in report["module_import_error"]


def test_driver_verified_session_forces_ssl(monkeypatch):
    driver = _load_driver()

    class FakeClientSession:
        async def _request(self, method, url, **kwargs):  # pragma: no cover - never awaited
            return None

    fake_aiohttp = types.ModuleType("aiohttp")
    fake_aiohttp.ClientSession = FakeClientSession
    monkeypatch.setitem(sys.modules, "aiohttp", fake_aiohttp)
    driver._CACHED_SESSION_CLASS = None
    session_class = driver._verified_session_class()
    assert session_class._request is not FakeClientSession._request
    assert session_class._force_verified({"ssl": False}) == {"ssl": True}
    assert driver._session_forces_verification() is True
