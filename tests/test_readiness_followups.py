"""Readiness audit 2026-10-25 follow-ups.

1. An unauthenticated ``instaloader`` run hung until the 120 s timeout. The runner
   now fails fast and exits 5, and the adapter records that as a skip.
2. ``leak_checkers`` reported skip/error records as ``breach`` entities, so a source
   that was never queried looked like breach data.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path
from uuid import uuid4

import pytest

from aletheia.adapters.leak_checkers import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    LeakCheckersAdapter,
)
from aletheia.adapters.social_geo_image import InstaloaderAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "docker" / "instaloader" / "runner.py"
LEAK_FIXTURE = ROOT / "tests" / "fixtures" / "leak_checkers.json"


def _request(kind, value):
    return AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=kind, value=value),
        legal_only=True,
        authorization_assertion="authorized readiness follow-up test",
    )


# ---------------------------------------------------------------- leak_checkers


def test_leak_checker_skip_records_are_not_breach_entities():
    payload = json.loads(LEAK_FIXTURE.read_text(encoding="utf-8"))
    result = LeakCheckersAdapter().parse(
        _request(SeedType.DOMAIN, "example.com"), None, json.dumps(payload), "", 0
    )
    by_source = {f.attributes["source"]: f for f in result.findings}
    for source in UNSUPPORTED_SUB_SOURCES:
        assert by_source[source].value == f"{source}:skipped"
        assert by_source[source].entity_type == EntityType.UNKNOWN
    for source in SUPPORTED_SUB_SOURCES:
        assert by_source[source].entity_type == EntityType.BREACH


def test_leak_checker_error_records_are_not_breach_entities():
    payload = {
        "input_value": "example.com",
        "sources": [{"source": "leakix", "error": "boom", "http_status": 500}],
    }
    result = LeakCheckersAdapter().parse(
        _request(SeedType.DOMAIN, "example.com"), None, json.dumps(payload), "", 0
    )
    (finding,) = result.findings
    assert finding.value == "leakix:error"
    assert finding.entity_type == EntityType.UNKNOWN
    assert finding.attributes["details"]["error"] == "boom"


def test_leak_checkers_descriptor_declares_unknown_output():
    outputs = LeakCheckersAdapter.descriptor.output_types
    assert EntityType.BREACH in outputs and EntityType.UNKNOWN in outputs


# ------------------------------------------------------------- instaloader adapter


def test_instaloader_blocked_run_is_recorded_as_skip_not_empty_result():
    stderr = "instagram blocked the unauthenticated profile lookup: LoginRequiredException: login required"
    result = InstaloaderAdapter().parse(_request(SeedType.USERNAME, "alice"), Path("."), "", stderr, 5)
    assert result.status == "partial"
    (finding,) = result.findings
    assert finding.value == "instaloader:skipped"
    assert finding.attributes["skipped"] is True
    assert "LoginRequiredException" in finding.attributes["reason"]
    assert not any(f.entity_type == EntityType.SOCIAL_ACCOUNT for f in result.findings)


def test_instaloader_clean_empty_result_is_not_a_skip():
    result = InstaloaderAdapter().parse(_request(SeedType.USERNAME, "alice"), Path("."), "", "profile not found: alice", 0)
    assert result.status == "succeeded"
    assert result.findings == []


# --------------------------------------------------------------- instaloader runner


class _Exc:
    """Fake ``instaloader.exceptions`` hierarchy mirroring the real one."""

    class InstaloaderException(Exception):
        pass

    class ConnectionException(InstaloaderException):
        pass

    class LoginRequiredException(InstaloaderException):
        pass

    class TooManyRequestsException(ConnectionException):
        pass

    class QueryReturnedBadRequestException(ConnectionException):
        pass

    class QueryReturnedNotFoundException(ConnectionException):
        pass

    class ProfileNotExistsException(InstaloaderException):
        pass


class _FakeProfile:
    behaviour = None  # callable(username) -> profile or raises
    username = full_name = biography = external_url = None
    followers = followees = mediacount = 0
    is_private = is_verified = False

    @staticmethod
    def from_username(context, username):
        return _FakeProfile.behaviour(username)


@pytest.fixture
def runner(monkeypatch):
    created = {}

    class FakeRateController:
        slept = None

        def __init__(self, context):
            self.context = context

        def sleep(self, secs):
            FakeRateController.slept = secs

    class FakeInstaloader:
        def __init__(self, **kwargs):
            created["kwargs"] = kwargs
            self.context = object()

    fake = types.ModuleType("instaloader")
    fake.RateController = FakeRateController
    fake.Instaloader = FakeInstaloader
    fake.Profile = _FakeProfile
    fake_exc = types.ModuleType("instaloader.exceptions")
    for name in vars(_Exc):
        if name.endswith("Exception"):
            setattr(fake_exc, name, getattr(_Exc, name))
    fake.exceptions = fake_exc
    monkeypatch.setitem(sys.modules, "instaloader", fake)
    monkeypatch.setitem(sys.modules, "instaloader.exceptions", fake_exc)
    spec = importlib.util.spec_from_file_location("instaloader_runner_under_test", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._created = created
    module._FakeRateController = FakeRateController
    return module


def _run(runner, monkeypatch, capsys, behaviour, username="alice"):
    _FakeProfile.behaviour = staticmethod(behaviour)
    monkeypatch.setattr(sys, "argv", ["runner.py", username])
    code = runner.main()
    out = capsys.readouterr()
    return code, out.out, out.err


def test_runner_health(runner, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["runner.py", "--health"])
    assert runner.main() == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_runner_success_prints_profile_json_and_uses_fail_fast_settings(runner, monkeypatch, capsys):
    def found(username):
        profile = _FakeProfile()
        profile.username = username
        profile.full_name = "Alice"
        return profile

    code, out, _ = _run(runner, monkeypatch, capsys, found)
    assert code == 0
    data = json.loads(out)
    assert data["username"] == "alice"
    assert data["profile_url"] == "https://www.instagram.com/alice/"
    kwargs = runner._created["kwargs"]
    assert kwargs["max_connection_attempts"] == 1
    assert kwargs["request_timeout"] == runner.REQUEST_TIMEOUT
    assert isinstance(kwargs["rate_controller"](object()), runner.FailFastRateController)


@pytest.mark.parametrize(
    "exc",
    [
        _Exc.LoginRequiredException("login required"),
        _Exc.TooManyRequestsException("429 Too Many Requests"),
        _Exc.QueryReturnedBadRequestException("400 Bad Request"),
        _Exc.ConnectionException("connection reset"),
        TimeoutError("no response within 45s"),
    ],
)
def test_runner_blocked_lookup_exits_5_with_reason(runner, monkeypatch, capsys, exc):
    def blocked(username):
        raise exc

    code, out, err = _run(runner, monkeypatch, capsys, blocked)
    assert code == 5
    assert out == ""
    assert "instagram blocked the unauthenticated profile lookup" in err
    assert type(exc).__name__ in err


@pytest.mark.parametrize(
    "exc", [_Exc.ProfileNotExistsException("nope"), _Exc.QueryReturnedNotFoundException("404")]
)
def test_runner_missing_profile_is_a_clean_empty_result(runner, monkeypatch, capsys, exc):
    def missing(username):
        raise exc

    code, out, err = _run(runner, monkeypatch, capsys, missing)
    assert code == 0
    assert out == ""
    assert "profile not found: alice" in err


def test_runner_rejects_bad_usernames(runner, monkeypatch, capsys):
    for bad in ("", "a/b", "a b"):
        monkeypatch.setattr(sys, "argv", ["runner.py", bad])
        assert runner.main() == 2
        capsys.readouterr()


def test_fail_fast_rate_controller_raises_on_long_waits_only(runner):
    controller = runner.FailFastRateController(object())
    with pytest.raises(_Exc.TooManyRequestsException, match="failing fast"):
        controller.sleep(runner.MAX_SLEEP_SECONDS + 1)
    controller.sleep(1)
    assert runner._FakeRateController.slept == 1


def test_runner_deadline_handler_raises_timeout(runner):
    with pytest.raises(TimeoutError, match=str(runner.DEADLINE_SECONDS)):
        runner._on_deadline(None, None)
