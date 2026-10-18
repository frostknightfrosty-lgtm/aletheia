#!/usr/bin/env python3
"""Aletheia driver for Zehef: email -> registered-account signals.

The driver runs only the 17 account-registration modules from the pinned
upstream checkout (``modules/accounts``). The paste-dump module (Google-dork
scraping), the HudsonRock stealer-log module, and the random
email-combination generator are never invoked, and the upstream self-update
check never runs; the reasons are recorded in RATE_LIMITS.md next to this
file.

Modes:
  --health    offline: verify the pinned checkout imports and print ``ok``.
  --selftest  offline: check the module inventory, exercise classification
              and detail parsing on samples, and import the pinned checkout.
  <email>     run the account checks and print one JSON document on stdout.

Why the palette patching: upstream modules signal a positive ("registered")
result by printing a line in green and a negative one in red (``lib/colors``)
and some print indented detail lines (``Username : value``). Instead of
classifying on ANSI escape sequences, the driver replaces the palette
constants in ``lib.colors`` with stable markers *before* the module package
is imported (each module does ``from lib.colors import *``), so status
classification never depends on terminal control codes.

Bounds: one request per service per run, sequential, no retries and no
pagination. Async modules get a 40s per-module timeout; the whole run is
bounded by a 240s hard deadline after which partial results are printed with
``deadline_exceeded: true`` and the process exits 3 (a hung upstream call in
one of the three synchronous modules must not stall a run indefinitely).
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import inspect
import io
import json
import os
import re
import sys
import threading

ZEHEF_DIR = os.environ.get("ZEHEF_DIR", "/opt/zehef")
PINNED_COMMIT = "5b0c120efe846eae944dfea9410f925ca3036103"

PER_MODULE_TIMEOUT_SECONDS = 40.0
HARD_DEADLINE_SECONDS = 240.0

GREEN_MARK = "[[ALETHEIA-GREEN]]"
RED_MARK = "[[ALETHEIA-RED]]"
_MARKERS = {
    "RED": RED_MARK,
    "GREEN": GREEN_MARK,
    "WHITE": "[[ALETHEIA-WHITE]]",
    "YELLOW": "[[ALETHEIA-YELLOW]]",
    "CYAN": "[[ALETHEIA-CYAN]]",
    "PURPLE": "[[ALETHEIA-PURPLE]]",
    "PINK": "[[ALETHEIA-PINK]]",
    "BLACK": "[[ALETHEIA-BLACK]]",
}
_MARKER_RE = re.compile("|".join(re.escape(mark) for mark in _MARKERS.values()))

# The 17 account modules of the pinned checkout in the upstream order used by
# lib/cli.py; Twitter's module attribute is named ``x``.
MODULE_NAMES = (
    "adobe", "bandlab", "chess", "deezer", "duolingo", "flickr", "github",
    "gravatar", "imgur", "instagram", "picsart", "pinterest", "pornhub",
    "protonmail", "spotify", "strava", "twitter",
)
_ATTRIBUTE_NAMES = {name: ("x" if name == "twitter" else name) for name in MODULE_NAMES}

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_DETAIL_RE = re.compile(r"^[^\S\n]*[\u251c\u2514]\u2500\u2500>\s*(?P<key>[^:]+?)\s*:\s*(?P<value>.+?)\s*$")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_DETAIL_KEYS = {
    "username": "username",
    "name": "name",
    "id": "id",
    "avatar": "avatar",
    "created on": "created_on",
    "update on": "updated_on",
    "account": "account",
}

_REAL_STDOUT = sys.stdout


def _clean(text: str) -> str:
    return _ANSI_RE.sub("", _MARKER_RE.sub("", text))


def _classify(raw_output: str) -> str:
    if GREEN_MARK in raw_output:
        return "registered"
    lowered = raw_output.casefold()
    if "error" in lowered or "exception" in lowered or "traceback" in lowered:
        return "error"
    if RED_MARK in raw_output:
        return "not_registered"
    return "no_signal"


def _parse_details(output: str) -> dict[str, str]:
    details: dict[str, str] = {}
    for line in output.splitlines():
        match = _DETAIL_RE.match(line)
        if match is None:
            continue
        key = _DETAIL_KEYS.get(match.group("key").strip().casefold())
        if key is None or key in details:
            continue
        value = match.group("value").strip()
        if value:
            details[key] = value
    return details


def _load_account_modules() -> list[tuple[str, object]]:
    if ZEHEF_DIR not in sys.path:
        sys.path.insert(0, ZEHEF_DIR)
    site_colors = importlib.import_module("lib.colors")
    for name, value in _MARKERS.items():
        setattr(site_colors, name, value)
    package = importlib.import_module("modules.accounts")
    modules: list[tuple[str, object]] = []
    for name in MODULE_NAMES:
        function = getattr(package, _ATTRIBUTE_NAMES[name], None)
        if not callable(function):
            raise RuntimeError(f"module '{name}' is missing from the pinned checkout")
        modules.append((name, function))
    return modules


async def _run_one(name: str, function, email: str) -> dict:
    buffer = io.StringIO()
    record: dict = {"service": name, "status": "no_signal", "details": {}, "output": ""}
    try:
        with contextlib.redirect_stdout(buffer):
            if inspect.iscoroutinefunction(function):
                await asyncio.wait_for(function(email), timeout=PER_MODULE_TIMEOUT_SECONDS)
            else:
                # The three synchronous modules use requests/httpx without a
                # per-call timeout; the hard deadline above bounds the run.
                await asyncio.to_thread(function, email)
    except asyncio.TimeoutError:
        record["status"] = "error"
        record["error"] = "timeout"
    except Exception as exc:  # upstream modules raise arbitrary exceptions
        record["status"] = "error"
        record["error"] = type(exc).__name__
    else:
        record["status"] = _classify(buffer.getvalue())
    cleaned = _clean(buffer.getvalue())
    record["output"] = cleaned[-4000:]
    if record["status"] == "registered":
        record["details"] = _parse_details(cleaned)
    return record


async def run_email(email: str, modules, state: dict | None = None) -> list[dict]:
    results: list[dict] = []
    if state is not None:
        state["results"] = results
    for name, function in modules:
        if state is not None:
            state["current_module"] = name
        results.append(await _run_one(name, function, email))
    if state is not None:
        state["current_module"] = None
    return results


def _deadline_abort(state: dict) -> None:
    document = {
        "sub_source": "zehef",
        "email": state.get("email"),
        "pinned_commit": PINNED_COMMIT,
        "deadline_exceeded": True,
        "current_module": state.get("current_module"),
        "modules": state.get("results", []),
    }
    _REAL_STDOUT.write(json.dumps(document, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()
    os._exit(3)


def health() -> int:
    try:
        modules = _load_account_modules()
    except Exception as exc:
        sys.stderr.write(f"module import failed: {type(exc).__name__}: {exc}\n")
        print("error")
        return 1
    sys.stderr.write(json.dumps({
        "pinned_commit": PINNED_COMMIT,
        "module_count": len(modules),
        "modules": [name for name, _ in modules],
    }, ensure_ascii=False) + "\n")
    print("ok")
    return 0


def selftest(loader=None) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool) -> None:
        checks.append({"name": name, "ok": bool(ok)})

    report: dict = {
        "zehef_selftest": "ok",
        "pinned_commit": PINNED_COMMIT,
        "module_count": len(MODULE_NAMES),
        "checks": checks,
    }
    check(
        "module_inventory",
        len(MODULE_NAMES) == 17
        and all(name in MODULE_NAMES for name in ("github", "instagram", "twitter", "protonmail"))
        and all(name not in MODULE_NAMES for name in ("pastedumper", "hudsonrock", "emails_gen")),
    )
    check("classify_registered", _classify(f"{GREEN_MARK}> Github\n") == "registered")
    check("classify_not_registered", _classify(f"{RED_MARK}> Imgur\n") == "not_registered")
    check("classify_error", _classify(f"{RED_MARK}> Instagram {_MARKERS['WHITE']}error: KeyError\n") == "error")
    check("classify_no_signal", _classify("") == "no_signal")
    sample = (
        f"{GREEN_MARK}> Github\n"
        "  \u251c\u2500\u2500> Username : octocat\n"
        "  \u251c\u2500\u2500> Created on : 2011-01-25 18:44:36\n"
        "  \u2514\u2500\u2500> Account : https://github.com/octocat\n"
    )
    details = _parse_details(_clean(sample))
    check(
        "detail_parsing",
        details.get("username") == "octocat"
        and details.get("created_on") == "2011-01-25 18:44:36"
        and details.get("account") == "https://github.com/octocat",
    )
    load = loader if loader is not None else _load_account_modules
    try:
        modules = load()
    except Exception as exc:
        check("checkout_import", False)
        report["checkout_import_error"] = f"{type(exc).__name__}: {exc}"
    else:
        check("checkout_import", len(modules) == len(MODULE_NAMES))
    if not all(item["ok"] for item in checks):
        report["zehef_selftest"] = "fail"
    return report


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: run_zehef.py <email> | --health | --selftest\n")
        return 2
    argument = argv[0]
    if argument == "--health":
        return health()
    if argument == "--selftest":
        report = selftest()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["zehef_selftest"] == "ok" else 1
    email = argument
    if not _EMAIL_RE.match(email):
        print(json.dumps({"sub_source": "zehef", "email": email, "error": "invalid email address"}))
        return 2
    try:
        modules = _load_account_modules()
    except Exception as exc:
        print(json.dumps({
            "sub_source": "zehef",
            "email": email,
            "error": f"checkout import failed: {type(exc).__name__}: {exc}",
        }, ensure_ascii=False))
        return 2
    state: dict = {"email": email, "results": [], "current_module": None}
    watchdog = threading.Timer(HARD_DEADLINE_SECONDS, _deadline_abort, args=(state,))
    watchdog.daemon = True
    watchdog.start()
    try:
        asyncio.run(run_email(email, modules, state))
    finally:
        watchdog.cancel()
    print(json.dumps({
        "sub_source": "zehef",
        "email": email,
        "pinned_commit": PINNED_COMMIT,
        "modules": state["results"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
