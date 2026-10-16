import importlib.util
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.adapters.leak_checkers import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    LeakCheckersAdapter,
)
from aletheia.core.models import AdapterRunRequest, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "leak_checkers.json"
RUNNER_PATH = ROOT / "docker" / "leak_checkers" / "runner.py"


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_runner():
    spec = importlib.util.spec_from_file_location("leak_checkers_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_request():
    return AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=SeedType.DOMAIN, value="example.com"),
        legal_only=True,
        authorization_assertion="authorized fixture test; no live source query",
    )


def test_supported_sources_are_documented_and_drop_reasons_are_present():
    runner = load_runner()
    assert runner.SUPPORTED_SUB_SOURCES == SUPPORTED_SUB_SOURCES
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES
    assert "leakix" in SUPPORTED_SUB_SOURCES
    assert "grayhatwarfare" in SUPPORTED_SUB_SOURCES
    assert "breachdirectory" in UNSUPPORTED_SUB_SOURCES
    assert "leak-lookup" in UNSUPPORTED_SUB_SOURCES
    assert "bron-vault" in UNSUPPORTED_SUB_SOURCES
    assert all("https://" in reason for reason in UNSUPPORTED_SUB_SOURCES.values())
    assert "403" in UNSUPPORTED_SUB_SOURCES["breachdirectory"]
    assert "written" in UNSUPPORTED_SUB_SOURCES["leak-lookup"]
    assert "self-hosted" in UNSUPPORTED_SUB_SOURCES["bron-vault"]


@parser_test("leak_checkers")
def test_parse_creates_findings_for_supported_sources():
    payload = load_fixture()
    adapter = LeakCheckersAdapter()
    result = adapter.parse(
        make_request(),
        workspace=None,
        stdout=json.dumps(payload),
        stderr="",
        exit_code=0,
    )
    assert result.status == "succeeded"
    by_source = {finding.attributes["source"]: finding for finding in result.findings}
    assert set(by_source) == set(SUPPORTED_SUB_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    assert by_source["leakix"].value == "LEAKIX:synthetic-event-fingerprint"
    assert by_source["grayhatwarfare"].value == "GRAYHAT:synthetic-file-id"
    for source, reason in UNSUPPORTED_SUB_SOURCES.items():
        assert by_source[source].attributes["details"] == {"skipped": True, "reason": reason}
    for finding in result.findings:
        raw = finding.attributes.get("raw_evidence")
        if raw:
            assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
                json.dumps(raw, sort_keys=True).encode()
            ).hexdigest()


def test_leakix_request_matches_official_search_contract(monkeypatch):
    runner = load_runner()
    monkeypatch.setenv("LEAKIX_API_KEY", "fixture-secret")
    calls = []

    def fake_fetch(url, headers=None):
        calls.append((url, headers))
        return ([{
            "event_type": "leak",
            "event_source": "SyntheticPlugin",
            "event_fingerprint": "synthetic-event-fingerprint",
            "host": "example.com",
            "ip": "192.0.2.1",
            "port": "443",
            "time": "2026-10-16T00:00:00Z",
            "summary": "must not be retained",
            "leak": {"stage": "open", "severity": "low", "credentials": {"password": "must not be retained"}},
        }], 200, None)

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch)
    result = runner.query_leakix("example.com")

    assert len(calls) == 1
    url, headers = calls[0]
    parsed = urlparse(url)
    assert parsed.netloc == "leakix.net"
    assert parsed.path == "/search"
    assert parse_qs(parsed.query) == {"scope": ["leak"], "q": ["example.com"], "page": ["0"]}
    assert headers["api-key"] == "fixture-secret"
    assert result.data["records"][0]["record_id"] == "synthetic-event-fingerprint"
    assert "summary" not in result.data["records"][0]
    assert "credentials" not in json.dumps(result.to_dict())
    assert "fixture-secret" not in json.dumps(result.to_dict())


def test_grayhatwarfare_request_matches_official_api_v2_contract(monkeypatch):
    runner = load_runner()
    monkeypatch.setenv("GRAYHATWARFARE_TOKEN", "fixture-secret")
    calls = []

    def fake_fetch(url, headers=None):
        calls.append((url, headers))
        return ({
            "meta": {"results": 1},
            "files": [{
                "id": "synthetic-file-id",
                "bucket": "example.invalid",
                "filename": "synthetic.txt",
                "fullPath": "fixture/synthetic.txt",
                "url": "https://example.invalid/fixture/synthetic.txt",
                "size": 12,
                "type": "aws",
                "lastModified": 0,
            }],
        }, 200, None)

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch)
    result = runner.query_grayhatwarfare("example.com")

    assert len(calls) == 1
    url, headers = calls[0]
    parsed = urlparse(url)
    assert parsed.netloc == "buckets.grayhatwarfare.com"
    assert parsed.path == "/api/v2/files"
    assert parse_qs(parsed.query) == {"keywords": ["example.com"], "limit": ["25"], "start": ["0"]}
    assert headers["Authorization"] == "Bearer fixture-secret"
    assert result.data["record_count"] == 1
    assert result.data["records"][0]["record_id"] == "synthetic-file-id"
    assert "fixture-secret" not in json.dumps(result.to_dict())


def test_runner_skips_missing_keys_and_reports_all_dropped_sources(monkeypatch):
    runner = load_runner()
    monkeypatch.delenv("LEAKIX_API_KEY", raising=False)
    monkeypatch.delenv("GRAYHATWARFARE_TOKEN", raising=False)

    sources = runner._run_for_input("domain", "example.com")
    by_source = {source["source"]: source for source in sources}

    assert set(by_source) == set(SUPPORTED_SUB_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    assert all(by_source[name]["skipped"] for name in SUPPORTED_SUB_SOURCES)
    assert all(by_source[name]["skipped"] for name in UNSUPPORTED_SUB_SOURCES)


def test_adapter_supports_domain_and_keyword_seed_types():
    adapter = LeakCheckersAdapter()
    assert adapter.supports(SeedType.DOMAIN)
    assert adapter.supports(SeedType.NAME)
    assert not adapter.supports(SeedType.IMAGE)
