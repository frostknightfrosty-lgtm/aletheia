"""Unit tests for the CI execution-evidence checker (``ci/pytest_summary.py``).

The checker is what turns "the suite passed" into "every test actually ran":
it cross-checks the JUnit XML against the pytest console summary and fails when
anything was skipped. These tests pin that behaviour, including the false-green
cases it exists to catch.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

CI_DIR = Path(__file__).resolve().parents[1] / "ci"
if str(CI_DIR) not in sys.path:
    sys.path.insert(0, str(CI_DIR))

import pytest_summary  # noqa: E402

JUNIT_TWO_PASSED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
  <testcase classname="tests.test_a" name="test_one" time="0.01"/>
  <testcase classname="tests.test_b" name="test_two" time="0.02"/>
</testsuite></testsuites>
"""

JUNIT_ONE_SKIPPED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
  <testcase classname="tests.test_a" name="test_one" time="0.01"/>
  <testcase classname="tests.test_b" name="test_two" time="0.01">
    <skipped message="ALETHEIA_STORAGE_REDIS is not set (no storage service configured)"/>
  </testcase>
</testsuite></testsuites>
"""

JUNIT_ONE_FAILED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1">
  <testcase classname="tests.test_a" name="test_one" time="0.01">
    <failure message="boom">traceback</failure>
  </testcase>
</testsuite></testsuites>
"""


def _write(tmp_path: Path, junit: str, console: str) -> tuple[Path, Path]:
    junit_path = tmp_path / "pytest-junit.xml"
    console_path = tmp_path / "pytest-full.log"
    junit_path.write_text(junit, encoding="utf-8")
    console_path.write_text(textwrap.dedent(console), encoding="utf-8")
    return junit_path, console_path


def test_clean_run_passes(tmp_path: Path) -> None:
    junit, console = _write(tmp_path, JUNIT_TWO_PASSED, "......\n2 passed, 1 warning in 3.21s\n")
    report = pytest_summary.build_report(junit, console)
    assert report["ok"] is True, report["problems"]
    assert report["junit_total"] == 2
    assert report["console_counts"]["passed"] == 2


def test_skip_in_junit_fails(tmp_path: Path) -> None:
    junit, console = _write(tmp_path, JUNIT_ONE_SKIPPED, "s.\n1 passed, 1 skipped, 1 warning in 3.21s\n")
    report = pytest_summary.build_report(junit, console)
    assert report["ok"] is False
    assert any("skipped in CI" in problem for problem in report["problems"])
    assert report["skipped_in_ci"][0]["test"] == "tests.test_b::test_two"


def test_skip_visible_only_in_console_still_fails(tmp_path: Path) -> None:
    """A module-level skip may not appear in JUnit; the console line still catches it."""
    junit, console = _write(tmp_path, JUNIT_TWO_PASSED, "..\n1 passed, 1 skipped in 3.21s\n")
    report = pytest_summary.build_report(junit, console)
    assert report["ok"] is False
    assert any("console summary reports 1 skipped" in problem for problem in report["problems"])


def test_failure_fails(tmp_path: Path) -> None:
    junit, console = _write(tmp_path, JUNIT_ONE_FAILED, "F\n1 failed in 0.50s\n")
    report = pytest_summary.build_report(junit, console)
    assert report["ok"] is False
    assert any("failed or errored" in problem for problem in report["problems"])
    assert report["failed"]


def test_passed_count_mismatch_fails(tmp_path: Path) -> None:
    junit, console = _write(tmp_path, JUNIT_TWO_PASSED, "..\n3 passed in 3.21s\n")
    report = pytest_summary.build_report(junit, console)
    assert report["ok"] is False
    assert any("but JUnit recorded" in problem for problem in report["problems"])


def test_passed_plus_skipped_must_equal_total(tmp_path: Path) -> None:
    """A skip must not also be reported as a count mismatch."""
    junit, console = _write(tmp_path, JUNIT_ONE_SKIPPED, "s.\n1 passed, 1 skipped, 1 warning in 3.21s\n")
    report = pytest_summary.build_report(junit, console)
    assert report["ok"] is False
    assert not any("but JUnit recorded" in problem for problem in report["problems"])
    assert any("skipped in CI" in problem for problem in report["problems"])


def test_missing_summary_line_fails(tmp_path: Path) -> None:
    junit, console = _write(tmp_path, JUNIT_TWO_PASSED, "no summary here\n")
    report = pytest_summary.build_report(junit, console)
    assert report["ok"] is False
    assert any("no pytest summary line" in problem for problem in report["problems"])
