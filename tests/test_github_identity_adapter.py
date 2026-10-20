"""Fixture/parser and driver tests for the github_identity adapter.

The parser test runs on ``tests/fixtures/github_identity.json`` — a synthetic
combined document in the shape ``docker/github_identity/run_github_identity.py``
emits. No live GitHub request is made by this test module.
"""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.github_identity import GithubIdentityAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "github_identity.json"
USERNAME = "octo-example"


def _request(value=USERNAME):
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.USERNAME, value=value)
    )


def _load_driver():
    path = ROOT / "docker" / "github_identity" / "run_github_identity.py"
    spec = importlib.util.spec_from_file_location("github_identity_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_github_identity_descriptor_scoping():
    adapter = GithubIdentityAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "github_identity"
    assert "GitHub" in descriptor.license
    assert descriptor.input_types == [SeedType.USERNAME]
    assert descriptor.output_types == [
        EntityType.SOCIAL_ACCOUNT, EntityType.TECHNICAL_FINDING
    ]
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.docker_image == "aletheia/github-identity:v1"
    assert descriptor.upstream == "https://docs.github.com/en/rest"
    assert adapter.supports(SeedType.USERNAME) is True
    assert adapter.supports(SeedType.NAME) is False


def test_github_identity_build_command_and_username_validation(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = GithubIdentityAdapter().build_command(_request("  Octo-Example  "), workspace)
    assert command == ["/work/username.txt"]
    assert (workspace / "username.txt").read_text(encoding="utf-8") == "Octo-Example\n"
    for bad in ("bad name", "-leading", "trailing-", "double--hyphen", "x" * 40):
        with pytest.raises(ValueError):
            GithubIdentityAdapter().build_command(_request(bad), workspace)


@parser_test("github_identity")
def test_github_identity_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = GithubIdentityAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert result.status == "succeeded"
    assert _values(result) == [
        "github_identity:event:123",
        "github_identity:gist:abc123",
        "github_identity:profile:octo-example",
        "github_identity:repo:octo-example/example-repo",
        "github_identity:run:ok",
        "github_identity:ssh:SHA256:vjuup/Z4aA7corfYUZagCiLLKA04fiuT4zsw9BAt2j8",
    ]
    assert len(result.findings) == 6
    assert result.findings[0].entity_type == EntityType.SOCIAL_ACCOUNT

    by_value = {finding.value: finding for finding in result.findings}
    run = by_value["github_identity:run:ok"]
    assert run.attributes["username"] == USERNAME
    assert run.attributes["repo_count"] == 1
    assert run.attributes["ssh_key_count"] == 1
    assert run.attributes["errors"] == []
    assert run.attributes["rate_limit"]["remaining"] == 54

    profile = by_value["github_identity:profile:octo-example"]
    assert profile.entity_type == EntityType.SOCIAL_ACCOUNT
    assert profile.attributes["platform"] == "github"
    assert profile.attributes["name"] == "Octo Example"
    assert "email" not in profile.attributes
    assert profile.provenance.confidence == 0.6

    repo = by_value["github_identity:repo:octo-example/example-repo"]
    assert repo.entity_type == EntityType.TECHNICAL_FINDING
    assert repo.attributes["language"] == "Python"
    assert repo.attributes["topics"] == ["osint", "synthetic"]
    assert repo.provenance.confidence == 0.5

    key = by_value[
        "github_identity:ssh:SHA256:vjuup/Z4aA7corfYUZagCiLLKA04fiuT4zsw9BAt2j8"
    ]
    assert key.entity_type == EntityType.TECHNICAL_FINDING
    assert key.attributes["key_type"] == "ssh-ed25519"
    assert key.attributes["key_source"] == "api"
    assert "key" not in key.attributes


def test_github_identity_parser_partial_and_malformed():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["status"] = "partial"
    payload["errors"] = ["events: HTTP 403: rate limit exceeded"]
    result = GithubIdentityAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "partial"
    assert result.findings[0].attributes["errors"] == [
        "events: HTTP 403: rate limit exceeded"
    ]
    assert len(result.findings) == 6

    result = GithubIdentityAdapter().parse(_request(), Path("."), "not json", "", 1)
    assert _values(result) == ["github_identity:run:error"]
    assert result.status == "partial"
    assert len(result.findings) == 1


def test_github_identity_driver_normalises_email_exclusion_and_fingerprints():
    driver = _load_driver()
    combined = {
        "source": "github_identity",
        "status": "ok",
        "username": USERNAME,
        "profile": driver._SAMPLE_PROFILE,
        "repos": driver._SAMPLE_REPOS,
        "gists": driver._SAMPLE_GISTS,
        "events": driver._SAMPLE_EVENTS,
        "ssh_keys": driver._keys_from_api(driver._SAMPLE_KEYS),
        "rate_limit": {"limit": 60, "remaining": 54, "used": 6, "reset": 1},
        "errors": [],
    }
    normalised = driver._normalise(combined)
    assert normalised["status"] == "ok"
    assert normalised["profile"]["login"] == "octo-example"
    assert "email" not in normalised["profile"]
    assert "private@example.org" not in json.dumps(normalised)
    assert len(normalised["repos"]) == 1
    assert len(normalised["gists"]) == 1
    assert len(normalised["events"]) == 1
    assert normalised["ssh_keys"][0]["fingerprint"].startswith("SHA256:")
    assert "key" not in normalised["ssh_keys"][0]

    parsed = driver._fingerprint(driver._SAMPLE_KEY)
    assert parsed is not None
    assert parsed[0] == "ssh-ed25519"
    assert driver._fingerprint("not-a-key") is None
    assert driver._fingerprint("ssh-ed25519 !!!notbase64!!!") is None

    dots = driver._keys_from_text(driver._SAMPLE_KEY + "\n" + driver._SAMPLE_KEY + "\n")
    assert len(dots) == 1
    assert dots[0]["source"] == "dotkeys"


def test_github_identity_driver_bounds_and_invalid_documents():
    driver = _load_driver()
    bounded = driver._normalise({
        "source": "github_identity",
        "status": "ok",
        "username": USERNAME,
        "profile": driver._SAMPLE_PROFILE,
        "repos": driver._SAMPLE_REPOS * 20,
        "gists": driver._SAMPLE_GISTS * 20,
        "events": driver._SAMPLE_EVENTS * 20,
        "ssh_keys": driver._keys_from_api(driver._SAMPLE_KEYS) * 20,
        "errors": ["x"] * 20,
    })
    assert bounded["status"] == "partial"
    assert len(bounded["repos"]) == driver.MAX_REPOS
    assert len(bounded["gists"]) == driver.MAX_GISTS
    assert len(bounded["events"]) == driver.MAX_EVENTS
    assert len(bounded["ssh_keys"]) == 1
    assert len(bounded["errors"]) == driver.MAX_ERRORS

    for bad in ({}, {"source": "other", "username": USERNAME},
                {"source": "github_identity", "username": "bad name"}):
        with pytest.raises(ValueError):
            driver._normalise(bad)


def test_github_identity_driver_name_file_and_args(tmp_path):
    driver = _load_driver()
    good = tmp_path / "username.txt"
    good.write_text("  Octo-Example \n", encoding="utf-8")
    assert driver._read_username(good) == "Octo-Example"

    with pytest.raises(ValueError):
        driver._read_username(tmp_path / "missing.txt")
    bad = tmp_path / "bad.txt"
    bad.write_text("not a username\n", encoding="utf-8")
    with pytest.raises(ValueError):
        driver._read_username(bad)
    multiline = tmp_path / "multiline.txt"
    multiline.write_text("one\ntwo\n", encoding="utf-8")
    with pytest.raises(ValueError):
        driver._read_username(multiline)

    assert driver._parse_args(["--health"]).health is True
    assert driver._parse_args(["--selftest"]).selftest is True
    parsed = driver._parse_args(["--normalize", "combined.json"])
    assert parsed.normalize == "combined.json"
    assert parsed.username_file is None
    assert driver._parse_args(["username.txt"]).username_file == "username.txt"
