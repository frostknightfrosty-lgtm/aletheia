#!/usr/bin/env python3
"""Phase 14 storage conformance evidence, run against the configured backends.

The file backend is always exercised (it is the default store). Every networked
backend named in ``ALETHEIA_STORAGE_<NAME>`` is exercised when its environment
variable is set, and reported as *unconfigured* otherwise. A backend is only
reported as conforming when every check in the shared contract passes.

Only the standard library plus the Aletheia package is used.

Output: one JSON document on stdout (``--json``) and a human line on stderr.
Exit code 0 only when every configured backend conforms.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Make ``aletheia`` importable when run from the repo root without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from aletheia.storage import (  # noqa: E402
    BACKENDS,
    ENV_VARS,
    FILE_BACKEND,
    NETWORKED_BACKENDS,
    open_backend,
)
from aletheia.storage.conformance import conform  # noqa: E402

DEFAULT_OUTPUT = "ci-artifacts/storage-conformance.json"


def _run_backend(name: str, target: str) -> dict:
    backend = open_backend(name, target)
    try:
        result = conform(backend)
    except Exception as exc:  # noqa: BLE001 - a backend that cannot even be probed fails
        result = {
            "backend": name,
            "ok": False,
            "checks": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        try:
            backend.close()
        except Exception:  # noqa: BLE001 - close is best effort
            pass
    return result


def build_report() -> dict:
    results: list[dict] = []
    unconfigured: list[str] = []

    with tempfile.TemporaryDirectory(prefix="aletheia-storage-") as tmp:
        file_result = _run_backend(FILE_BACKEND, str(Path(tmp) / "graphs"))
        file_result["configured"] = True
        results.append(file_result)

    for name in NETWORKED_BACKENDS:
        value = os.environ.get(ENV_VARS[name])
        if not value:
            unconfigured.append(name)
            continue
        result = _run_backend(name, value)
        result["configured"] = True
        results.append(result)

    configured = [row["backend"] for row in results]
    passing = [row["backend"] for row in results if row.get("ok")]
    return {
        "ok": all(row.get("ok") for row in results),
        "configured": configured,
        "unconfigured": unconfigured,
        "passing": passing,
        "backends": results,
        "known_backends": sorted(BACKENDS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the full JSON report on stdout")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="path for the JSON report")
    args = parser.parse_args()

    report = build_report()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    total, passed = len(report["configured"]), len(report["passing"])
    verdict = "PASS" if report["ok"] else "FAIL"
    print(f"STORAGE CONFORMANCE: {verdict} \u2014 {passed}/{total} backends conform", file=sys.stderr)
    if report["unconfigured"]:
        print(f"unconfigured (skipped): {', '.join(report['unconfigured'])}", file=sys.stderr)
    print(f"report: {output}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
