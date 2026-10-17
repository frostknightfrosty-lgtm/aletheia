#!/usr/bin/env python3
"""Assert that CI actually executed every test (no silent skips).

The Docker integration tests and the Phase-14 storage service tests skip when
Docker or the storage services are absent. That is correct on a developer
machine, but in CI a *skip* there would be a false green: the suite would pass
while the container/service checks never ran. This script makes that impossible
by cross-checking two independent records of the same run:

  * the JUnit XML written by ``--junitxml`` (per-test outcome), and
  * the pytest console summary line in the tee'd log.

A run passes only when both agree, the failure/error counts are zero, and the
skip count is zero. Exit code 1 otherwise.

Usage::

    python ci/pytest_summary.py \
        --junit ci-artifacts/pytest-junit.xml \
        --console ci-artifacts/pytest-full.log \
        --output ci-artifacts/pytest-summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SKIP_CLI_UNAVAILABLE = "Docker CLI unavailable"
SKIP_DOCS = "docs/SKIPPED_IN_CI.md"

SUMMARY = re.compile(
    r"(?P<body>(?:\d+\s+(?:passed|failed|error|errors|skipped|xfailed|xpassed|deselected|warnings?|warning)"
    r"(?:,\s*)?)+)\s*in\s+[\d.]+s"
)
COUNTS = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed|deselected|warning|warnings)")


def parse_junit(path: Path) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()
    cases = root.iter("testcase")
    total = 0
    skipped: list[dict] = []
    failed: list[str] = []
    for case in cases:
        total += 1
        name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
        if case.find("skipped") is not None:
            node = case.find("skipped")
            skipped.append({"test": name, "reason": (node.get("message") or "").strip() if node is not None else ""})
        for tag in ("failure", "error"):
            node = case.find(tag)
            if node is not None:
                failed.append(f"{name} [{tag}] {(node.get('message') or '').strip()}")
    return {"total": total, "skipped": skipped, "failed": failed}


def parse_console(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(SUMMARY.finditer(text))
    if not matches:
        return {"found": False, "raw": "", "counts": {}}
    raw = matches[-1].group("body")
    counts: dict[str, int] = {}
    for value, label in COUNTS.findall(raw):
        key = "errors" if label.startswith("error") else "warnings" if label.startswith("warning") else label
        counts[key] = counts.get(key, 0) + int(value)
    return {"found": True, "raw": raw.strip(), "counts": counts}


def build_report(junit_path: Path, console_path: Path) -> dict:
    junit = parse_junit(junit_path)
    console = parse_console(console_path)

    skipped = junit["skipped"]
    reasons = sorted({entry["reason"] for entry in skipped})
    console_skipped = console["counts"].get("skipped")
    console_passed = console["counts"].get("passed")
    console_failed = console["counts"].get("failed", 0) + console["counts"].get("errors", 0)

    problems: list[str] = []
    if not console["found"]:
        problems.append("no pytest summary line found in the console log")
    if junit["failed"]:
        problems.append(f"{len(junit['failed'])} test(s) failed or errored")
    if skipped:
        problems.append(f"{len(skipped)} test(s) skipped in CI: {', '.join(sorted(entry['test'] for entry in skipped))}")
    if console_skipped:
        problems.append(f"console summary reports {console_skipped} skipped")
    if console_failed:
        problems.append(f"console summary reports {console_failed} failed/errored")
    if console["found"] and console_passed is not None and (console_passed + (console_skipped or 0)) != junit["total"]:
        problems.append(
            f"console reports {console_passed} passed + {console_skipped or 0} skipped "
            f"but JUnit recorded {junit['total']} test cases"
        )

    return {
        "ok": not problems,
        "problems": problems,
        "junit_total": junit["total"],
        "console_summary": console["raw"],
        "console_counts": console["counts"],
        "skipped_in_ci": skipped,
        "skip_reasons": reasons,
        "failed": junit["failed"],
        "note": (
            "Docker integration tests and storage service tests must EXECUTE in CI. "
            f"See {SKIP_DOCS} for why they still skip on a machine without Docker."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", default="ci-artifacts/pytest-junit.xml")
    parser.add_argument("--console", default="ci-artifacts/pytest-full.log")
    parser.add_argument("--output", default="ci-artifacts/pytest-summary.json")
    args = parser.parse_args()

    report = build_report(Path(args.junit), Path(args.console))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if report["ok"]:
        print(
            f"TEST EXECUTION: PASS \u2014 {report['junit_total']} test cases executed, 0 skipped in CI",
            file=sys.stderr,
        )
    else:
        print("TEST EXECUTION: FAIL", file=sys.stderr)
        for problem in report["problems"]:
            print(f"  - {problem}", file=sys.stderr)
    print(f"report: {output}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
