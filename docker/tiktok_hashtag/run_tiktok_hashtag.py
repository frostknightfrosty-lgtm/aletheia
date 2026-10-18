#!/usr/bin/env python3
"""Aletheia driver for tiktok-hashtag-analysis (Bellingcat).

Modes:
  run_tiktok_hashtag.py <hashtag>   public hashtag sample (bounded)
  run_tiktok_hashtag.py --health    import/pin/browser presence check
  run_tiktok_hashtag.py --selftest  offline checks (no network)

Design notes (see docker/tiktok_hashtag/RATE_LIMITS.md):

* Headless only. This driver calls
  ``tiktok_hashtag_analysis.base._fetch_hashtag_data(hashtag=..., limit=...,
  headed=False)`` directly, so the upstream headed retry in
  ``TikTokDownloader.get_hashtag_posts`` is structurally unreachable.
* TikTokApi 6.2.2 calls ``stealth_async(page)`` unconditionally inside
  ``create_sessions()``. Per docs/LEGAL_MODEL.md the browser-stealth patching
  is neutralized by replacing ``TikTokApi.tiktok.stealth_async`` with a no-op
  before any session is created. The run fails closed if that patch target is
  missing. Nothing else about the client is altered.
* Bot-detection responses (empty response, captcha page, invalid JSON) are
  recorded as an honest ``blocked`` status with the exception text preserved;
  they are never retried beyond the pinned client's own bounded transient
  playwright-error retry, never challenged, and no cookies or ms_tokens are
  ever supplied.
* No media downloads, no plots, no config files. The output is a single JSON
  document: status, bounded post sample (id, url, author handle, create time,
  description excerpt, co-hashtags), and co-hashtag counts.
"""

import asyncio
import json
import os
import re
import sys
import threading
from collections import Counter

CHECKOUT = os.environ.get("TIKTOK_CHECKOUT", "/opt/tiktok")
PINNED_COMMIT = "2a4af674efc4af7c7d592053ec3f475555f37694"

SOURCE = "tiktok-hashtag-analysis"
SUB_SOURCE = "hashtag-search"

DEFAULT_LIMIT = 40
DESCRIPTION_EXCERPT_CHARS = 160
MAX_COHASHTAGS_PER_POST = 20
MAX_COHASHTAG_COUNTS = 50
FETCH_TIMEOUT_SECONDS = 180.0
HARD_DEADLINE_SECONDS = 240.0

_HASHTAG_RE = re.compile(r"^#?[A-Za-z0-9_]{1,64}$")
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.]{1,32}$")

_REAL_STDOUT = sys.stdout


async def _noop_stealth(page):
    """Replacement for TikTokApi's browser-stealth patch (see module docstring)."""
    return None


def _neutralize_stealth():
    """Disable the dependency's stealth patching; fail closed if absent."""
    import TikTokApi

    module = getattr(TikTokApi, "tiktok", None)
    if module is None or not hasattr(module, "stealth_async"):
        return False
    module.stealth_async = _noop_stealth
    return getattr(module, "stealth_async", None) is _noop_stealth


def _load_upstream():
    """Import the pinned checkout; returns (fetch_function, version)."""
    if CHECKOUT not in sys.path:
        sys.path.insert(0, CHECKOUT)
    from tiktok_hashtag_analysis import base
    from tiktok_hashtag_analysis.version import VERSION

    function = base._fetch_hashtag_data
    if not callable(function):
        raise RuntimeError("_fetch_hashtag_data missing from the pinned checkout")
    return function, VERSION


def _pin_file_matches():
    try:
        with open(os.path.join(CHECKOUT, "PINNED_COMMIT"), "r", encoding="utf-8") as handle:
            return handle.read().strip() == PINNED_COMMIT
    except OSError:
        return False


def _chromium_present():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        path = playwright.chromium.executable_path
    return bool(path) and os.path.isfile(path)


def _normalize_post(raw):
    """Normalize one raw TikTokApi video dictionary; None when unusable."""
    if not isinstance(raw, dict):
        return None
    video_id = raw.get("id")
    if not (isinstance(video_id, str) and video_id.isdigit() and 5 <= len(video_id) <= 25):
        return None
    author = raw.get("author")
    handle = author.get("uniqueId") if isinstance(author, dict) else None
    if not (isinstance(handle, str) and _HANDLE_RE.match(handle)):
        return None
    cohashtags = []
    text_extra = raw.get("textExtra")
    if isinstance(text_extra, list):
        for item in text_extra:
            if not isinstance(item, dict):
                continue
            name = item.get("hashtagName")
            if isinstance(name, str):
                name = name.strip().lower()
                if name and name not in cohashtags:
                    cohashtags.append(name)
    description = raw.get("desc")
    if not isinstance(description, str):
        description = ""
    create_time = raw.get("createTime")
    if not isinstance(create_time, int):
        create_time = None
    return {
        "id": video_id,
        "url": f"https://www.tiktok.com/@{handle}/video/{video_id}",
        "author": handle,
        "create_time": create_time,
        "desc_excerpt": description[:DESCRIPTION_EXCERPT_CHARS],
        "cohashtags": cohashtags[:MAX_COHASHTAGS_PER_POST],
    }


def _fetch(fetch, hashtag, limit, state, blocked_types=None):
    """Run one bounded hashtag fetch; maps outcomes onto honest statuses."""
    if blocked_types is None:
        from TikTokApi.exceptions import (
            CaptchaException,
            EmptyResponseException,
            InvalidJSONException,
        )

        blocked_types = (EmptyResponseException, CaptchaException, InvalidJSONException)
    state["stage"] = "fetch"
    try:
        raw_posts = asyncio.run(
            asyncio.wait_for(
                fetch(hashtag=hashtag, limit=limit, headed=False),
                timeout=FETCH_TIMEOUT_SECONDS,
            )
        )
    except asyncio.TimeoutError:
        return "error", [], f"fetch timed out after {int(FETCH_TIMEOUT_SECONDS)}s"
    except blocked_types as exc:
        return "blocked", [], f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return "error", [], f"{type(exc).__name__}: {exc}"
    return "ok", raw_posts if isinstance(raw_posts, list) else [], None


def _deadline_abort(state):
    document = {
        "source": SOURCE,
        "sub_source": SUB_SOURCE,
        "hashtag": state.get("hashtag"),
        "pinned_commit": PINNED_COMMIT,
        "status": "error",
        "deadline_exceeded": True,
        "stage": state.get("stage"),
        "posts": [],
        "error": f"hard deadline of {int(HARD_DEADLINE_SECONDS)}s exceeded",
    }
    _REAL_STDOUT.write(json.dumps(document, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()
    os._exit(3)


def health():
    details = {"pinned_commit": PINNED_COMMIT}
    try:
        _, version = _load_upstream()
        details["checkout_version"] = version
        details["pin_file"] = _pin_file_matches()
        details["stealth_neutralized"] = _neutralize_stealth()
        details["chromium_present"] = _chromium_present()
    except Exception as exc:
        sys.stderr.write(f"health check failed: {type(exc).__name__}: {exc}\n")
        print("error")
        return 1
    sys.stderr.write(json.dumps(details, ensure_ascii=False) + "\n")
    if not (details["pin_file"] and details["stealth_neutralized"] and details["chromium_present"]):
        print("error")
        return 1
    print("ok")
    return 0


def selftest(loader=None, stealth_probe=None, chromium_probe=None):
    checks = []

    def check(name, ok):
        checks.append({"name": name, "ok": bool(ok)})

    report = {
        "tiktok_hashtag_selftest": "ok",
        "pinned_commit": PINNED_COMMIT,
        "checks": checks,
    }
    check("pin_file", _pin_file_matches())
    load = loader if loader is not None else _load_upstream
    try:
        fetch, version = load()
    except Exception as exc:
        check("checkout_import", False)
        check("fetch_signature", False)
        report["checkout_import_error"] = f"{type(exc).__name__}: {exc}"
    else:
        check("checkout_import", True)
        report["checkout_version"] = version
        signature_ok = False
        try:
            parameters = __import__("inspect").signature(fetch).parameters
            signature_ok = (
                list(parameters) == ["hashtag", "limit", "headed"]
                and parameters["headed"].default is False
            )
        except (TypeError, ValueError):
            signature_ok = False
        check("fetch_signature", signature_ok)
    stealth = stealth_probe if stealth_probe is not None else _neutralize_stealth
    try:
        check("stealth_neutralized", bool(stealth()))
    except Exception:
        check("stealth_neutralized", False)
    chromium = chromium_probe if chromium_probe is not None else _chromium_present
    try:
        check("chromium_present", bool(chromium()))
    except Exception:
        check("chromium_present", False)
    check(
        "hashtag_validation",
        bool(_HASHTAG_RE.match("#osint"))
        and bool(_HASHTAG_RE.match("OSINT"))
        and not _HASHTAG_RE.match("two words")
        and not _HASHTAG_RE.match("")
        and not _HASHTAG_RE.match("#")
        and not _HASHTAG_RE.match("x" * 65),
    )
    sample = {
        "id": "7301234567890123456",
        "desc": "sunset vibes #NewMusic",
        "createTime": 1710000000,
        "author": {"uniqueId": "example_user"},
        "textExtra": [
            {"hashtagName": "NewMusic"},
            {"hashtagName": "newmusic"},
            {"hashtagName": "osint"},
            {"hashtagName": ""},
            {"notAHashtag": True},
        ],
    }
    normalized = _normalize_post(sample)
    check(
        "post_normalization",
        normalized
        == {
            "id": "7301234567890123456",
            "url": "https://www.tiktok.com/@example_user/video/7301234567890123456",
            "author": "example_user",
            "create_time": 1710000000,
            "desc_excerpt": "sunset vibes #NewMusic",
            "cohashtags": ["newmusic", "osint"],
        }
        and _normalize_post({"id": "abc", "author": {"uniqueId": "example_user"}}) is None
        and _normalize_post({"id": "7301234567890123456", "author": {"uniqueId": "bad handle"}}) is None
        and _normalize_post({"id": "7301234567890123456", "author": {}}) is None,
    )
    if not all(item["ok"] for item in checks):
        report["tiktok_hashtag_selftest"] = "fail"
    return report


def main(argv):
    if len(argv) != 1:
        sys.stderr.write("usage: run_tiktok_hashtag.py <hashtag> | --health | --selftest\n")
        return 2
    argument = argv[0]
    if argument == "--health":
        return health()
    if argument == "--selftest":
        report = selftest()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["tiktok_hashtag_selftest"] == "ok" else 1
    hashtag = argument.strip().lower()
    if not _HASHTAG_RE.match(hashtag):
        print(json.dumps({
            "source": SOURCE,
            "sub_source": SUB_SOURCE,
            "hashtag": argument,
            "pinned_commit": PINNED_COMMIT,
            "status": "invalid_hashtag",
            "posts": [],
            "error": "expected 1-64 characters from [A-Za-z0-9_], with an optional leading '#'",
        }, ensure_ascii=False))
        return 2
    hashtag = hashtag.lstrip("#")
    document = {
        "source": SOURCE,
        "sub_source": SUB_SOURCE,
        "hashtag": hashtag,
        "pinned_commit": PINNED_COMMIT,
        "stealth_neutralized": False,
        "requested_limit": DEFAULT_LIMIT,
        "status": "error",
        "fetched": 0,
        "posts": [],
        "cohashtag_counts": {},
    }
    try:
        fetch, version = _load_upstream()
        stealth_ok = _neutralize_stealth()
    except Exception as exc:
        document["error"] = f"driver setup failed: {type(exc).__name__}: {exc}"
        print(json.dumps(document, ensure_ascii=False))
        return 1
    document["checkout_version"] = version
    if not stealth_ok:
        document["error"] = "stealth patch target missing in the pinned client; refusing to run (fail closed)"
        print(json.dumps(document, ensure_ascii=False))
        return 1
    document["stealth_neutralized"] = True
    state = {"hashtag": hashtag, "stage": "setup"}
    watchdog = threading.Timer(HARD_DEADLINE_SECONDS, _deadline_abort, args=(state,))
    watchdog.daemon = True
    watchdog.start()
    try:
        status, raw_posts, error = _fetch(fetch, hashtag, DEFAULT_LIMIT, state)
    finally:
        watchdog.cancel()
    seen = set()
    posts = []
    for raw in raw_posts:
        post = _normalize_post(raw)
        if post is None or post["id"] in seen:
            continue
        seen.add(post["id"])
        posts.append(post)
    counts = Counter()
    for post in posts:
        for name in post["cohashtags"]:
            if name != hashtag:
                counts[name] += 1
    if status == "ok" and not posts:
        status = "empty"
    document["status"] = status
    document["fetched"] = len(posts)
    document["posts"] = posts
    document["cohashtag_counts"] = dict(
        sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:MAX_COHASHTAG_COUNTS]
    )
    if error:
        document["error"] = error
    print(json.dumps(document, ensure_ascii=False))
    return 0 if status in {"ok", "empty", "blocked"} else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
