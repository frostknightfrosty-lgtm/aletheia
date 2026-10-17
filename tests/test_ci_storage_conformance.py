"""Unit tests for the storage conformance evidence script.

Run 39078543221 reported ``STORAGE CONFORMANCE: PASS`` while no storage service
had actually started, because every backend counted as "unconfigured" and an
unconfigured backend was treated as acceptable. ``--require-all`` (used by CI)
makes that impossible. These tests pin both behaviours without needing a service.
"""

from __future__ import annotations

import sys
from pathlib import Path

CI_DIR = Path(__file__).resolve().parents[1] / "ci"
if str(CI_DIR) not in sys.path:
    sys.path.insert(0, str(CI_DIR))

import storage_conformance  # noqa: E402

from aletheia.storage import NETWORKED_BACKENDS, FILE_BACKEND  # noqa: E402


def _ok_runner(name: str, target: str) -> dict:
    return {"backend": name, "ok": True, "checks": [{"name": "health", "ok": True, "skipped": False, "detail": ""}]}


def _bad_runner(name: str, target: str) -> dict:
    if name == FILE_BACKEND:
        return _ok_runner(name, target)
    return {"backend": name, "ok": False, "checks": []}


def test_unconfigured_backends_pass_by_default() -> None:
    report = storage_conformance.build_report(configured={}, runner=_ok_runner)
    assert report["ok"] is True
    assert report["unconfigured"] == list(NETWORKED_BACKENDS)
    assert report["passing"] == [FILE_BACKEND]


def test_require_all_fails_when_a_backend_is_unconfigured() -> None:
    report = storage_conformance.build_report(require_all=True, configured={}, runner=_ok_runner)
    assert report["ok"] is False
    assert any("were not configured" in problem for problem in report["problems"])
    # The file backend still ran and passed; the failure is purely the gap.
    assert report["passing"] == [FILE_BACKEND]


def test_require_all_passes_when_every_backend_is_configured_and_conforms() -> None:
    configured = {name: f"stub://{name}" for name in NETWORKED_BACKENDS}
    report = storage_conformance.build_report(require_all=True, configured=configured, runner=_ok_runner)
    assert report["ok"] is True, report["problems"]
    assert report["unconfigured"] == []
    assert set(report["passing"]) == {FILE_BACKEND, *NETWORKED_BACKENDS}


def test_a_failing_backend_fails_the_report() -> None:
    configured = {name: f"stub://{name}" for name in NETWORKED_BACKENDS}
    report = storage_conformance.build_report(require_all=True, configured=configured, runner=_bad_runner)
    assert report["ok"] is False
    assert any("failed conformance" in problem for problem in report["problems"])
