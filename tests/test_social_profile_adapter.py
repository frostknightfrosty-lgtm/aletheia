"""Fixture/parser and bounded-request tests for the social-profile batch."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.adapters.social_profile import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    SocialProfileAdapter,
    SocialProfileFinding,
)
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "social_profile.json"


def _request(seed_type: SeedType = SeedType.COMPANY_NAME, value: str = "Example Corp") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=seed_type, value=value),
        legal_only=True,
        authorization_assertion="Synthetic fixture parser test.",
    )


def _load_runner():
    path = ROOT / "docker" / "social_profile" / "runner.py"
    spec = importlib.util.spec_from_file_location("social_profile_runner_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@parser_test("social_profile")
def test_parse_synthetic_fixture_covers_supported_and_dropped_sources():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    result = SocialProfileAdapter().parse(_request(), Path("."), json.dumps(fixture), "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 2
    assert all(isinstance(finding, SocialProfileFinding) for finding in result.findings)
    assert all(finding.entity_type == EntityType.SOCIAL_ACCOUNT for finding in result.findings)
    allowed = {"name", "username", "email", "company", "source_url"}
    assert all(set(finding.attributes) <= allowed for finding in result.findings)
    crosslinked = next(f for f in result.findings if f.attributes.get("company"))
    assert crosslinked.attributes == {
        "name": "alex example",
        "username": "alex-example",
        "company": "Example Corp",
        "source_url": "https://www.linkedin.com/in/alex-example",
    }
    slinky = next(f for f in result.findings if f.attributes.get("username") == "example_user")
    assert slinky.attributes == {
        "username": "example_user",
        "source_url": "https://github.com/example_user",
    }
    assert {"crosslinked", "slinky"} == set(SUPPORTED_SUB_SOURCES)
    assert {"tiktok-hashtag-analysis", "zehef"} == set(UNSUPPORTED_SUB_SOURCES)
    assert all(f.provenance.source_url.startswith("https://") for f in result.findings)


def test_adapter_supports_company_names_and_https_profile_urls():
    adapter = SocialProfileAdapter()
    company = _request(SeedType.COMPANY_NAME, "Example Corp")
    profile = _request(SeedType.URL, "https://github.com/example_user")

    assert adapter.supports(SeedType.COMPANY_NAME)
    assert adapter.supports(SeedType.URL)
    assert adapter.build_command(company, Path(".")) == ["company_name", "Example Corp"]
    assert adapter.build_command(profile, Path(".")) == ["url", "https://github.com/example_user"]
    assert not adapter.supports(SeedType.EMAIL)


def test_parser_discards_unsafe_url_and_unapproved_output_fields():
    payload = {
        "sources": [
            {
                "source": "crosslinked",
                "skipped": False,
                "data": {
                    "records": [
                        {
                            "name": "not emitted",
                            "username": "unsafe",
                            "job_title": "must not persist",
                            "source_url": "https://fake-linkedin.com/in/unsafe",
                        },
                        {
                            "name": "not emitted either",
                            "source_url": "http://www.linkedin.com/in/insecure",
                        },
                    ]
                },
            }
        ]
    }
    result = SocialProfileAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_partial_source_error_keeps_bounded_findings():
    payload = {
        "sources": [
            {
                "source": "crosslinked",
                "skipped": False,
                "error": "bing: HTTP 429; stopped without redirect or retry",
                "data": {
                    "records": [
                        {
                            "name": "alex example",
                            "username": "alex-example",
                            "company": "Example Corp",
                            "source_url": "https://www.linkedin.com/in/alex-example",
                        }
                    ]
                },
            }
        ]
    }
    result = SocialProfileAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)

    assert result.status == "partial"
    assert result.exit_code == 1
    assert len(result.findings) == 1
    assert "HTTP 429" in result.stderr_tail


def test_crosslinked_uses_at_most_one_https_page_per_engine(monkeypatch):
    runner = _load_runner()
    calls = []

    class FakeCrossLinked:
        url = {
            "google": "https://www.google.com/search?q=site:linkedin.com/in+\"{}\"&num=100&start={}",
            "bing": "http://www.bing.com/search?q=\"{}\"+site:linkedin.com/in&first={}",
        }

        def __init__(self, *, search_engine, **_kwargs):
            self.search_engine = search_engine
            self.results = []

        def page_parser(self, _response):
            self.results = [
                {"name": "alex example", "url": "https://www.linkedin.com/in/alex-example", "title": "ignored"},
                {"name": "unsafe host", "url": "https://fake-linkedin.com/in/unsafe", "title": "ignored"},
            ]

    class FakeResponse:
        status_code = 200
        text = "ordinary search results"
        content = b"<html></html>"

    monkeypatch.setattr(runner, "_crosslinked_class", lambda: FakeCrossLinked)

    def fake_fetch(url):
        calls.append(url)
        return FakeResponse()

    monkeypatch.setattr(runner, "_fetch_search_page", fake_fetch)
    result = runner.query_crosslinked("ACME & Sons")

    assert len(calls) == 2
    assert calls[0].startswith("https://www.google.com/search?")
    assert calls[1].startswith("https://www.bing.com/search?")
    assert all("ACME%20%26%20Sons" in call for call in calls)
    assert result.error is None
    assert len(result.data["records"]) == 1
    assert result.data["records"][0]["source_url"] == "https://www.linkedin.com/in/alex-example"
    assert set(result.data["records"][0]) == {"name", "username", "company", "source_url"}


def test_crosslinked_stops_on_challenge_without_retry(monkeypatch):
    runner = _load_runner()
    calls = []

    class FakeCrossLinked:
        url = {
            "google": "https://www.google.com/search?q={}&num=100&start={}",
            "bing": "http://www.bing.com/search?q={}&first={}",
        }

        def __init__(self, *, search_engine, **_kwargs):
            self.search_engine = search_engine
            self.results = []

        def page_parser(self, _response):
            raise AssertionError("challenge page must not be parsed")

    monkeypatch.setattr(runner, "_crosslinked_class", lambda: FakeCrossLinked)

    def fake_fetch(url):
        calls.append(url)
        return SimpleNamespace(status_code=200, text="verify you are human captcha", content=b"")

    monkeypatch.setattr(runner, "_fetch_search_page", fake_fetch)
    result = runner.query_crosslinked("Example Corp")

    assert len(calls) == 2
    assert "google: search challenge returned" in result.error
    assert result.data["records"] == []


def test_slinky_uses_offline_pinned_helper(monkeypatch):
    runner = _load_runner()
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"id": "example_user", "url": "https://github.com/example_user"}),
            stderr="",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.query_slinky("https://github.com/example_user")

    assert captured["command"] == [runner.SLINKY_BINARY, "https://github.com/example_user"]
    assert captured["kwargs"]["timeout"] == 5
    assert captured["kwargs"]["check"] is False
    assert result.error is None
    assert result.data["records"] == [
        {"username": "example_user", "source_url": "https://github.com/example_user"}
    ]


def test_health_is_offline_and_reports_only_expected_sources(monkeypatch, capsys):
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_fetch_search_page",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("health must be offline")),
    )

    assert runner.main(["--health"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok"
    health = json.loads(captured.err)
    assert health["network_used"] is False
    assert {entry["source"] for entry in health["sub_sources"]} == (
        set(SUPPORTED_SUB_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    )
