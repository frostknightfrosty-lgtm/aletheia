#!/usr/bin/env python3
"""Aletheia driver for the pinned PicImageSearch checkout (kitUIN/PicImageSearch).

Scoped review: ``docker/picimagesearch/RATE_LIMITS.md``. Exactly five keyless
engines run per invocation (IQDB, 3D IQDB, Ascii2D colour search, the official
TraceMoe JSON API, and the official AnimeTrace JSON API -- one request each),
plus the official SauceNAO JSON API only when ``SAUCENAO_API_KEY`` is set; that
engine is reported as a recorded skip otherwise. The consumer-web scrapers
(google, google_lens, yandex, bing, baidu), the token-refresh scraper
(copyseeker), the turnstile-blocked lenso client, the TinEye web-app scrape,
and the adult-gallery EHentai engine are never imported or invoked.

Two documented deviations from pinned behaviour, both fail closed:

* the package ships a hardcoded browser user agent (network.DEFAULT_HEADERS);
  every engine is constructed with an explicit honest ``Aletheia/0.9.0
  (picimagesearch)`` header, which wins the case-insensitive merge in
  ``network._merge_headers``; the run path and the selftest refuse to run if
  any engine's effective client user agent is not the honest agent.
* the network layer verifies TLS by default (``create_ssl_context(verify=True)``)
  and the driver never passes ``verify_ssl``; the run path and the selftest
  refuse to run if any engine reports verification off.

Modes::

    run_picimagesearch.py --file /work/input.jpg
    run_picimagesearch.py --url https://example.com/photo.jpg
    run_picimagesearch.py --health
    run_picimagesearch.py --selftest
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading

CHECKOUT = os.environ.get("PICIMAGESEARCH_CHECKOUT", "/opt/picimagesearch")
PINNED_COMMIT = "784713e546273a09aae4b247a8b6f798825efafa"
HONEST_UA = "Aletheia/0.9.0 (picimagesearch)"

GATHER_TIMEOUT_SECONDS = 150.0
HARD_DEADLINE_SECONDS = 210.0
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

KEYLESS_ENGINES = ("iqdb", "iqdb3d", "ascii2d", "tracemoe", "animetrace")
ENGINE_KEYS = KEYLESS_ENGINES + ("sauce_nao",)
EXCLUDED_ENGINES = (
    "google",
    "google_lens",
    "yandex",
    "bing",
    "baidu",
    "copyseeker",
    "lenso",
    "tineye",
    "ehentai",
)
SAUCE_KEY_ENV = "SAUCENAO_API_KEY"

_HTTPS_URL_RE = re.compile(r"^https://[^\s]+$", re.IGNORECASE)
_BLOCKED_MARKERS = ("403", "429", "forbidden", "too many requests", "cloudflare", "turnstile")

_REAL_STDOUT = sys.stdout


def _pin_file_matches() -> bool:
    try:
        with open(os.path.join(CHECKOUT, "PINNED_COMMIT"), "r", encoding="utf-8") as handle:
            return handle.read().strip() == PINNED_COMMIT
    except OSError:
        return False


def _package_version() -> str:
    import PicImageSearch

    return str(getattr(PicImageSearch, "__version__", "") or "unknown")


def _load_engines(api_key: str | None = None) -> dict:
    """Construct the reviewed engine set with the honest user agent."""
    from PicImageSearch import AnimeTrace, Ascii2D, Iqdb, SauceNAO, TraceMoe

    common = {"headers": {"User-Agent": HONEST_UA}, "timeout": 30.0}
    engines: dict = {
        "iqdb": Iqdb(is_3d=False, **common),
        "iqdb3d": Iqdb(is_3d=True, **common),
        "ascii2d": Ascii2D(**common),
        "tracemoe": TraceMoe(**common),
        "animetrace": AnimeTrace(**common),
    }
    if api_key:
        engines["sauce_nao"] = SauceNAO(api_key=api_key, **common)
    return engines


def _ua_of(engine) -> str:
    """Effective user agent of a constructed engine's HTTP client."""
    try:
        manager = engine._client_manager()
        network = getattr(manager, "client", None)
        client = getattr(network, "client", None)
        headers = getattr(client, "headers", None)
        if headers is None:
            return ""
        getter = getattr(headers, "get", None)
        if callable(getter):
            return str(getter("user-agent", "") or "")
        return str(headers)
    except Exception:
        return ""


def _validate_file(path: str) -> str | None:
    try:
        if not os.path.isfile(path):
            return None
        size = os.path.getsize(path)
    except OSError:
        return None
    if size <= 0 or size > MAX_UPLOAD_BYTES:
        return None
    return path


def _validate_url(value: str) -> str | None:
    return value if _HTTPS_URL_RE.match(value) else None


def _parse_args(argv: list[str]):
    if len(argv) == 2 and argv[0] == "--file" and argv[1]:
        return ("file", argv[1])
    if len(argv) == 2 and argv[0] == "--url" and argv[1]:
        return ("url", argv[1])
    return None


def _engine_request(key: str, engine, image_url: str | None, image_bytes: bytes | None) -> dict:
    """Replicate exactly the pinned engine's single search request.

    The pinned engines make one POST per search (the Ascii2D feature search,
    which would issue a second GET, is never enabled) and never paginate.
    Replicating the request directly keeps the HTTP status code observable for
    honest ``blocked`` accounting.
    """
    if key in ("iqdb", "iqdb3d"):
        if image_url:
            return {"method": "post", "url": engine.base_url, "data": {"url": image_url}, "files": None}
        return {"method": "post", "url": engine.base_url, "data": {}, "files": {"file": image_bytes}}
    if key == "ascii2d":
        endpoint = "uri" if image_url else "file"
        if image_url:
            return {
                "method": "post",
                "url": f"{engine.base_url}/{endpoint}",
                "data": {"uri": image_url},
                "files": None,
            }
        return {
            "method": "post",
            "url": f"{engine.base_url}/{endpoint}",
            "data": None,
            "files": {"file": image_bytes},
        }
    if key == "tracemoe":
        params: dict = {"anilistInfo": "", "cutBorders": "true"}
        if image_url:
            params["url"] = image_url
            return {"method": "post", "url": engine.base_url, "params": params, "files": None}
        return {"method": "post", "url": engine.base_url, "params": params, "files": {"file": image_bytes}}
    if key == "animetrace":
        if image_url:
            return {"method": "post", "url": engine.base_url, "json": {"url": image_url}}
        return {"method": "post", "url": engine.base_url, "files": {"file": image_bytes}, "data": None}
    if key == "sauce_nao":
        params = engine.params
        if image_url:
            params = params.add("url", image_url)
            return {"method": "post", "url": engine.base_url, "params": params, "files": None}
        return {"method": "post", "url": engine.base_url, "params": params, "files": {"file": image_bytes}}
    raise ValueError(f"unreviewed engine key: {key}")


def _build_response(key: str, resp):
    from PicImageSearch.model import (
        AnimeTraceResponse,
        Ascii2DResponse,
        IqdbResponse,
        SauceNAOResponse,
        TraceMoeResponse,
    )

    if key in ("iqdb", "iqdb3d"):
        return IqdbResponse(resp.text, resp.url)
    if key == "ascii2d":
        return Ascii2DResponse(resp.text, resp.url)
    if key == "tracemoe":
        return TraceMoeResponse(json.loads(resp.text), resp.url, mute=False, size=None)
    if key == "animetrace":
        return AnimeTraceResponse(json.loads(resp.text), resp.url)
    if key == "sauce_nao":
        payload = json.loads(resp.text)
        payload["status_code"] = int(resp.status_code)
        return SauceNAOResponse(payload, resp.url)
    raise ValueError(f"unreviewed engine key: {key}")


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _normalize_iqdb(response):
    items = []
    buckets = (("primary", getattr(response, "raw", None)), ("more", getattr(response, "more", None)))
    for match_list, bucket in buckets:
        for item in bucket or []:
            if item is None:
                continue
            other = []
            for source in getattr(item, "other_source", None) or []:
                if isinstance(source, dict) and _text(source.get("url")):
                    other.append({"source": _text(source.get("source")), "url": source["url"]})
            items.append(
                {
                    "match_list": match_list,
                    "content": _text(getattr(item, "content", "")),
                    "page_url": _text(getattr(item, "url", "")),
                    "source": _text(getattr(item, "source", "")),
                    "other_sources": other,
                    "thumbnail": _text(getattr(item, "thumbnail", "")),
                    "size": _text(getattr(item, "size", "")),
                    "similarity": float(getattr(item, "similarity", 0.0) or 0.0),
                }
            )
    return items, {"result_url": _text(getattr(response, "url", ""))}


def _normalize_ascii2d(response):
    items = []
    for item in getattr(response, "raw", None) or []:
        urls = []
        for entry in getattr(item, "url_list", None) or []:
            href = _text(getattr(entry, "href", ""))
            if href:
                urls.append({"href": href, "text": _text(getattr(entry, "text", ""))})
        items.append(
            {
                "page_url": _text(getattr(item, "url", "")),
                "hash": _text(getattr(item, "hash", "")),
                "detail": _text(getattr(item, "detail", "")),
                "thumbnail": _text(getattr(item, "thumbnail", "")),
                "title": _text(getattr(item, "title", "")),
                "author": _text(getattr(item, "author", "")),
                "author_url": _text(getattr(item, "author_url", "")),
                "urls": urls,
            }
        )
    return items, {"result_url": _text(getattr(response, "url", ""))}


def _normalize_tracemoe(response):
    items = []
    for item in getattr(response, "raw", None) or []:
        items.append(
            {
                "filename": _text(getattr(item, "filename", "")),
                "episode": _number(getattr(item, "episode", None)),
                "from": _number(getattr(item, "From", None)),
                "to": _number(getattr(item, "To", None)),
                "similarity": float(getattr(item, "similarity", 0.0) or 0.0),
                "video": _text(getattr(item, "video", "")),
                "image": _text(getattr(item, "image", "")),
                "anilist_id": _number(getattr(item, "anilist_id", None)),
                "title_romaji": _text(getattr(item, "title_romaji", "")),
                "title_english": _text(getattr(item, "title_english", "")),
                "title_native": _text(getattr(item, "title_native", "")),
                "is_adult": bool(getattr(item, "isAdult", False)),
                "format": _text(getattr(item, "format", "")),
            }
        )
    return items, {
        "result_url": _text(getattr(response, "url", "")),
        "frame_count": _number(getattr(response, "frameCount", None)),
        "api_error": _text(getattr(response, "error", "")),
    }


def _normalize_animetrace(response):
    items = []
    for item in getattr(response, "raw", None) or []:
        characters = []
        for character in getattr(item, "characters", None) or []:
            name = _text(getattr(character, "name", ""))
            work = _text(getattr(character, "work", ""))
            if name or work:
                characters.append({"name": name, "work": work})
        items.append(
            {
                "box": list(getattr(item, "box", None) or []),
                "box_id": _text(getattr(item, "box_id", "")),
                "characters": characters,
            }
        )
    return items, {
        "result_url": _text(getattr(response, "url", "")),
        "code": _number(getattr(response, "code", None)),
        "ai": bool(getattr(response, "ai", False)),
        "trace_id": _text(getattr(response, "trace_id", "")),
    }


def _normalize_sauce_nao(response):
    items = []
    for item in getattr(response, "raw", None) or []:
        ext_urls = [url for url in getattr(item, "ext_urls", None) or [] if _text(url)]
        items.append(
            {
                "page_url": _text(getattr(item, "url", "")),
                "similarity": float(getattr(item, "similarity", 0.0) or 0.0),
                "thumbnail": _text(getattr(item, "thumbnail", "")),
                "index_id": _number(getattr(item, "index_id", None)),
                "index_name": _text(getattr(item, "index_name", "")),
                "hidden": _number(getattr(item, "hidden", None)),
                "title": _text(getattr(item, "title", "")),
                "ext_urls": ext_urls,
                "author": _text(getattr(item, "author", "")),
                "author_url": _text(getattr(item, "author_url", "")),
                "source": _text(getattr(item, "source", "")),
            }
        )
    return items, {
        "result_url": _text(getattr(response, "url", "")),
        "short_remaining": _number(getattr(response, "short_remaining", None)),
        "long_remaining": _number(getattr(response, "long_remaining", None)),
        "api_status": _number(getattr(response, "status", None)),
    }


_NORMALIZERS = {
    "iqdb": _normalize_iqdb,
    "iqdb3d": _normalize_iqdb,
    "ascii2d": _normalize_ascii2d,
    "tracemoe": _normalize_tracemoe,
    "animetrace": _normalize_animetrace,
    "sauce_nao": _normalize_sauce_nao,
}


def _looks_blocked(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _BLOCKED_MARKERS)


def _engine_result(status: str, error: str = "", result_url: str = "", items: list | None = None, **extra) -> dict:
    result = {
        "status": status,
        "error": error,
        "result_url": result_url,
        "count": len(items or []),
        "items": items or [],
    }
    result.update(extra)
    return result


async def _run_engine(key: str, engine, image_url: str | None, image_bytes: bytes | None) -> dict:
    try:
        payload = _engine_request(key, engine, image_url, image_bytes)
        resp = await engine._send_request(**payload)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        status = "blocked" if _looks_blocked(message) else "error"
        return _engine_result(status, error=message[:300])
    status_code = int(getattr(resp, "status_code", 0) or 0)
    result_url = _text(getattr(resp, "url", ""))
    if status_code in (401, 403, 429):
        return _engine_result("blocked", error=f"HTTP {status_code}", result_url=result_url)
    if status_code >= 500:
        return _engine_result("error", error=f"HTTP {status_code}", result_url=result_url)
    try:
        parsed = _build_response(key, resp)
    except Exception as exc:
        message = f"response could not be parsed: {type(exc).__name__}: {exc}"
        status = "blocked" if _looks_blocked(message) else "error"
        return _engine_result(status, error=message[:300], result_url=result_url)
    items, meta = _NORMALIZERS[key](parsed)
    result_url = meta.pop("result_url", result_url)
    if key == "tracemoe" and not items and meta.get("api_error"):
        return _engine_result("error", error=str(meta["api_error"])[:300], result_url=result_url, **meta)
    status = "ok" if items else "empty"
    return _engine_result(status, result_url=result_url, items=items, **meta)


def _derive_status(results: dict) -> str:
    statuses = [
        entry.get("status")
        for entry in results.values()
        if isinstance(entry, dict) and entry.get("status") != "skipped"
    ]
    if not statuses:
        return "empty"
    if "ok" in statuses:
        return "ok"
    if "empty" in statuses:
        return "empty"
    if all(status == "blocked" for status in statuses):
        return "blocked"
    return "error"


async def _execute(engines: dict, image_url: str | None, image_bytes: bytes | None) -> dict:
    results: dict = {}
    for key in KEYLESS_ENGINES:
        results[key] = await _run_engine(key, engines[key], image_url, image_bytes)
    if "sauce_nao" in engines:
        results["sauce_nao"] = await _run_engine("sauce_nao", engines["sauce_nao"], image_url, image_bytes)
    else:
        results["sauce_nao"] = {
            "status": "skipped",
            "reason": "no api key (set SAUCENAO_API_KEY to enable)",
            "result_url": "",
            "count": 0,
            "items": [],
        }
    return results


def _deadline_abort(state):
    document = {
        "source": "PicImageSearch",
        "sub_source": "reverse-image-search",
        "pinned_commit": PINNED_COMMIT,
        "target": state.get("target"),
        "target_kind": state.get("target_kind"),
        "status": "error",
        "deadline_exceeded": True,
        "stage": state.get("stage"),
        "engines": {},
        "error": f"hard deadline of {int(HARD_DEADLINE_SECONDS)}s exceeded",
    }
    _REAL_STDOUT.write(json.dumps(document, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()
    os._exit(3)


def health() -> int:
    details = {"pinned_commit": PINNED_COMMIT}
    try:
        details["checkout_version"] = _package_version()
        engines = _load_engines(os.environ.get(SAUCE_KEY_ENV))
        details["engine_bindings"] = len(engines)
        details["ua_honest"] = all("Aletheia/0.9.0" in _ua_of(engine) for engine in engines.values())
        details["tls_verified"] = all(bool(getattr(engine, "verify_ssl", None)) for engine in engines.values())
        details["pin_file"] = _pin_file_matches()
    except Exception as exc:
        sys.stderr.write(f"health check failed: {type(exc).__name__}: {exc}\n")
        print("error")
        return 1
    sys.stderr.write(json.dumps(details, ensure_ascii=False) + "\n")
    if details.get("engine_bindings", 0) < len(KEYLESS_ENGINES):
        print("error")
        return 1
    if not (details["ua_honest"] and details["tls_verified"] and details["pin_file"]):
        print("error")
        return 1
    print("ok")
    return 0


def _normalization_ok() -> bool:
    from types import SimpleNamespace as NS

    try:
        items, _ = _normalize_iqdb(
            NS(
                raw=[
                    NS(
                        content="Best match",
                        url="https://a.example/1",
                        source="s",
                        other_source=[{"source": "o", "url": "https://b.example/2"}],
                        thumbnail="",
                        size="",
                        similarity=91.2,
                    )
                ],
                more=[],
                url="https://iqdb.org/x",
            )
        )
        if not (len(items) == 1 and items[0]["page_url"] == "https://a.example/1"):
            return False
        if items[0]["other_sources"][0]["url"] != "https://b.example/2":
            return False
        items, _ = _normalize_ascii2d(
            NS(
                raw=[
                    NS(
                        hash="h",
                        detail="d",
                        thumbnail="",
                        title="t",
                        author="a",
                        author_url="",
                        url="https://c.example/3",
                        url_list=[NS(href="https://d.example/4", text="x")],
                    )
                ],
                url="",
            )
        )
        if items[0]["urls"][0]["href"] != "https://d.example/4":
            return False
        items, _ = _normalize_tracemoe(
            NS(
                raw=[
                    NS(
                        filename="f",
                        episode=1,
                        From=1.0,
                        To=2.0,
                        similarity=90.0,
                        video="https://e.example/v",
                        image="https://e.example/i",
                        anilist_id=1,
                        title_romaji="r",
                        title_english="e",
                        title_native="n",
                        isAdult=False,
                        format="TV",
                    )
                ],
                url="",
                frameCount=1,
                error="",
            )
        )
        if items[0]["video"] != "https://e.example/v" or items[0]["episode"] != 1:
            return False
        items, _ = _normalize_animetrace(
            NS(
                raw=[NS(box=[1.0], box_id="b", characters=[NS(name="c", work="w")])],
                url="",
                code=0,
                ai=False,
                trace_id="t",
            )
        )
        if items[0]["characters"][0]["name"] != "c":
            return False
        items, _ = _normalize_sauce_nao(
            NS(
                raw=[
                    NS(
                        similarity=95.0,
                        thumbnail="",
                        index_id=5,
                        index_name="i",
                        hidden=0,
                        title="t",
                        url="",
                        ext_urls=["https://f.example/5"],
                        author="a",
                        author_url="",
                        source="s",
                    )
                ],
                url="https://saucenao.com/search.php",
                short_remaining=5,
                long_remaining=100,
                status=0,
            )
        )
        return items[0]["ext_urls"] == ["https://f.example/5"]
    except Exception:
        return False


def selftest(loader=None, ua_probe=None, package_probe=None) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    report = {
        "picimagesearch_selftest": "ok",
        "pinned_commit": PINNED_COMMIT,
        "checks": checks,
    }

    check("pin_file", _pin_file_matches())

    version = "unavailable"
    try:
        version = (package_probe or _package_version)()
        check("package_import", bool(version) and version != "unavailable", str(version))
    except Exception as exc:
        check("package_import", False, f"{type(exc).__name__}: {exc}")
    report["package_version"] = version

    engines: dict = {}
    load = loader if loader is not None else _load_engines
    try:
        engines = load(os.environ.get(SAUCE_KEY_ENV))
    except Exception as exc:
        check("engine_construction", False, f"{type(exc).__name__}: {exc}")
    else:
        check(
            "engine_construction",
            len(engines) >= len(KEYLESS_ENGINES) and set(KEYLESS_ENGINES) <= set(engines),
            f"engines={sorted(engines)}",
        )
    report["engine_bindings"] = len(engines)

    probe = ua_probe if ua_probe is not None else _ua_of
    if engines:
        try:
            agents = {key: probe(engine) for key, engine in sorted(engines.items())}
        except Exception:
            agents = {}
        check(
            "ua_honest",
            bool(agents) and all("Aletheia/0.9.0" in agent for agent in agents.values()),
            "; ".join(f"{key}={agent}" for key, agent in agents.items()),
        )
        check(
            "tls_verified",
            all(bool(getattr(engine, "verify_ssl", None)) for engine in engines.values()),
        )
    else:
        check("ua_honest", False, "no engines constructed")
        check("tls_verified", False, "no engines constructed")

    check(
        "target_validation",
        bool(_validate_url("https://example.com/photo.jpg"))
        and _validate_url("http://example.com/photo.jpg") is None
        and _validate_url("ftp://example.com/photo.jpg") is None
        and _validate_file(__file__) is not None
        and _validate_file(os.path.join(CHECKOUT, "does-not-exist.jpg")) is None,
    )

    check(
        "engine_scoping",
        ENGINE_KEYS == KEYLESS_ENGINES + ("sauce_nao",)
        and len(KEYLESS_ENGINES) == 5
        and len(set(KEYLESS_ENGINES)) == 5,
    )

    check(
        "excluded_scope",
        isinstance(EXCLUDED_ENGINES, tuple)
        and len(EXCLUDED_ENGINES) >= 9
        and not (set(EXCLUDED_ENGINES) & set(ENGINE_KEYS)),
    )

    check("normalization", _normalization_ok())

    if not all(item["ok"] for item in checks):
        report["picimagesearch_selftest"] = "fail"
    return report


def main(argv: list[str]) -> int:
    if argv == ["--health"]:
        return health()
    if argv == ["--selftest"]:
        report = selftest()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["picimagesearch_selftest"] == "ok" else 1

    parsed = _parse_args(argv)
    if parsed is None:
        sys.stderr.write(
            "usage: run_picimagesearch.py --file <path> | --url <https image url> | --health | --selftest\n"
        )
        return 2
    target_kind, raw_target = parsed

    document = {
        "source": "PicImageSearch",
        "sub_source": "reverse-image-search",
        "pinned_commit": PINNED_COMMIT,
        "checkout_version": "unavailable",
        "user_agent": HONEST_UA,
        "tls_verified": False,
        "target": raw_target,
        "target_kind": target_kind,
        "status": "error",
        "engines": {},
    }

    if target_kind == "url":
        target_url = _validate_url(raw_target)
        target_file = None
    else:
        target_file = _validate_file(raw_target)
        target_url = None
    if target_url is None and target_file is None:
        document["status"] = "invalid_target"
        document["error"] = (
            "expected an https:// image URL or an existing image file "
            f"(at most {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"
        )
        print(json.dumps(document, ensure_ascii=False))
        return 2

    try:
        api_key = os.environ.get(SAUCE_KEY_ENV) or None
        engines = _load_engines(api_key)
        document["checkout_version"] = _package_version()
    except Exception as exc:
        document["error"] = f"driver setup failed: {type(exc).__name__}: {exc}"
        print(json.dumps(document, ensure_ascii=False))
        return 1

    tls_ok = all(bool(getattr(engine, "verify_ssl", None)) for engine in engines.values())
    ua_ok = all("Aletheia/0.9.0" in _ua_of(engine) for engine in engines.values())
    document["tls_verified"] = bool(tls_ok)
    if not tls_ok:
        document["error"] = "an engine does not verify TLS; refusing to run (fail closed)"
        print(json.dumps(document, ensure_ascii=False))
        return 1
    if not ua_ok:
        document["error"] = (
            "the honest user agent is not in effect for every engine; refusing to run (fail closed)"
        )
        print(json.dumps(document, ensure_ascii=False))
        return 1

    requested = list(KEYLESS_ENGINES) + (["sauce_nao"] if "sauce_nao" in engines else [])
    document["requested_engines"] = requested

    image_url = target_url
    image_bytes = None
    if image_url is None:
        with open(target_file, "rb") as handle:
            image_bytes = handle.read()

    state = {"target": raw_target, "target_kind": target_kind, "stage": "engines"}
    watchdog = threading.Timer(HARD_DEADLINE_SECONDS, _deadline_abort, args=(state,))
    watchdog.daemon = True
    watchdog.start()
    try:
        results = asyncio.run(asyncio.wait_for(_execute(engines, image_url, image_bytes), GATHER_TIMEOUT_SECONDS))
        document["engines"] = results
        document["reported_engines"] = sorted(results)
        document["status"] = _derive_status(results)
    except asyncio.TimeoutError:
        document["status"] = "error"
        document["error"] = f"gather timeout of {int(GATHER_TIMEOUT_SECONDS)}s exceeded"
    except Exception as exc:
        document["status"] = "error"
        document["error"] = f"driver run failed: {type(exc).__name__}: {exc}"
    finally:
        watchdog.cancel()

    print(json.dumps(document, ensure_ascii=False))
    return 0 if document["status"] in {"ok", "empty", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
