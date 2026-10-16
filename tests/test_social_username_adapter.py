"""Fixture/parser and bounded-request tests for the social-username batch."""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from parser_test_marker import parser_test

from aletheia.adapters.social_username import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    SocialUsernameAdapter,
    SocialUsernameFinding,
)
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "social_username.json"


def _request(value: str = "alice") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=SeedType.USERNAME, value=value),
        legal_only=True,
        authorization_assertion="Synthetic fixture parser test.",
    )


def _load_runner():
    path = ROOT / "docker" / "social_username" / "runner.py"
    spec = importlib.util.spec_from_file_location("social_username_runner_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@parser_test("social_username")
def test_parse_synthetic_fixture_emits_only_bounded_public_profile_fields():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    result = SocialUsernameAdapter().parse(_request(), Path("."), json.dumps(fixture), "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 2
    assert all(isinstance(finding, SocialUsernameFinding) for finding in result.findings)
    assert all(finding.entity_type == EntityType.SOCIAL_ACCOUNT for finding in result.findings)
    assert {finding.attributes["source"] for finding in result.findings} == set(SUPPORTED_SUB_SOURCES)
    assert all(
        set(finding.attributes)
        <= {"source", "platform", "username", "display_name", "profile_url"}
        for finding in result.findings
    )
    assert {finding.attributes["profile_url"] for finding in result.findings} == {
        "https://mastodon.social/@alice",
        "https://github.com/alice",
    }
    assert all(finding.provenance.source_url == finding.attributes["profile_url"] for finding in result.findings)
    assert {"owasp-socialosintlm", "scrawler"} == set(UNSUPPORTED_SUB_SOURCES)


def test_adapter_supports_only_username_seeds():
    adapter = SocialUsernameAdapter()
    request = _request("alice")

    assert adapter.supports(SeedType.USERNAME)
    assert adapter.build_command(request, Path(".")) == ["username", "alice"]
    assert not adapter.supports(SeedType.EMAIL)


def test_parser_requires_exact_matches_discoverability_and_https_urls():
    payload = {
        "sources": [
            {
                "source": "masto",
                "data": {
                    "records": [
                        {"username": "alice", "profile_url": "https://mastodon.social/@alice", "discoverable": False},
                        {"username": "alice2", "profile_url": "https://mastodon.social/@alice2", "discoverable": True},
                        {"username": "alice", "profile_url": "http://mastodon.social/@alice", "discoverable": True},
                    ]
                },
            },
            {
                "source": "octosuite",
                "data": {
                    "records": [
                        {"username": "alice", "profile_url": "https://evil.example/alice"},
                    ]
                },
            },
        ]
    }
    result = SocialUsernameAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_partial_source_error_preserves_other_source_findings():
    payload = {
        "sources": [
            {"source": "masto", "error": "HTTP 429; stopped without redirect or retry", "data": {"records": []}},
            {
                "source": "octosuite",
                "data": {"records": [{"username": "alice", "profile_url": "https://github.com/alice"}]},
            },
        ]
    }
    result = SocialUsernameAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)

    assert result.status == "partial"
    assert result.exit_code == 1
    assert len(result.findings) == 1
    assert "HTTP 429" in result.stderr_tail


def test_masto_is_one_bounded_search_and_ignores_non_discoverable_results(monkeypatch):
    runner = _load_runner()
    captured = {}
    response = _response(
        {
            "accounts": [
                {"username": "alice", "display_name": "Alice", "url": "https://mastodon.social/@alice", "discoverable": True},
                {"username": "alice2", "url": "https://mastodon.social/@alice2", "discoverable": True},
                {"username": "alice", "url": "https://mastodon.social/@private", "discoverable": False},
            ]
        }
    )
    _mock_opener(monkeypatch, runner, captured, response)
    result = runner.query_masto("alice")

    assert result.error is None
    assert urlsplit(captured["url"])._replace(query="").geturl() == runner.MASTO_SEARCH_URL
    assert parse_qs(urlsplit(captured["url"]).query) == {"q": ["alice"], "type": ["accounts"], "limit": ["5"]}
    assert captured["timeout"] == 5
    assert any(isinstance(handler, runner.ProxyHandler) and handler.proxies == {} for handler in captured["handlers"])
    assert any(isinstance(handler, runner._NoRedirectHandler) for handler in captured["handlers"])
    assert result.data["records"] == [
        {
            "username": "alice",
            "display_name": "Alice",
            "profile_url": "https://mastodon.social/@alice",
            "discoverable": True,
        }
    ]


def test_masto_does_not_contact_unapproved_instances(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "build_opener",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unsupported instance must not be contacted")),
    )

    result = runner.query_masto("alice@private.example")

    assert result.skipped is True
    assert "no other instance" in result.skip_reason


def test_octosuite_uses_one_exact_public_github_user_endpoint(monkeypatch):
    runner = _load_runner()
    captured = {}
    response = _response(
        {
            "login": "alice",
            "name": "Alice Example",
            "html_url": "https://github.com/alice",
            "email": "public-email-must-not-be-emitted@example.test",
        }
    )
    _mock_opener(monkeypatch, runner, captured, response)
    result = runner.query_octosuite("alice")

    assert result.error is None
    assert captured["url"] == "https://api.github.com/users/alice"
    assert captured["timeout"] == 5
    assert any(isinstance(handler, runner.ProxyHandler) and handler.proxies == {} for handler in captured["handlers"])
    assert any(isinstance(handler, runner._NoRedirectHandler) for handler in captured["handlers"])
    assert result.data["records"] == [
        {"username": "alice", "profile_url": "https://github.com/alice", "display_name": "Alice Example"}
    ]
    assert "email" not in result.data["records"][0]


def test_rate_limit_error_is_reported_without_retry(monkeypatch):
    runner = _load_runner()

    class FakeOpener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 429, "Too Many Requests", None, io.BytesIO(b""))

    captured = {}

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return FakeOpener()

    monkeypatch.setattr(runner, "build_opener", fake_build_opener)
    result = runner.query_octosuite("alice")

    assert result.http_status == 429
    assert result.error == "HTTP 429; stopped without redirect or retry"


def test_health_does_not_make_network_requests(monkeypatch, capsys):
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "build_opener",
        lambda: (_ for _ in ()).throw(AssertionError("health must not create a session")),
    )
    monkeypatch.setattr(runner.importlib.metadata, "version", lambda name: "5.1.0")

    assert runner.main(["--health"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok"
    health = json.loads(captured.err)
    assert health["network_used"] is False
    assert health["octosuite_version"] == "5.1.0"
    assert {item["source"] for item in health["sub_sources"]} == (
        set(SUPPORTED_SUB_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    )


def _response(payload):
    body = json.dumps(payload).encode("utf-8")
    return SimpleNamespace(
        status=200,
        read=lambda _size: body,
        __enter__=lambda self: self,
        __exit__=lambda self, *_args: None,
    )


def _mock_opener(monkeypatch, runner, captured, response):
    class FakeResponse:
        status = response.status

        def read(self, _size):
            return response.read(_size)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class FakeOpener:
        def open(self, request, timeout):
            captured.update(url=request.full_url, timeout=timeout)
            return FakeResponse()

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return FakeOpener()

    monkeypatch.setattr(runner, "build_opener", fake_build_opener)
