"""Search-engine and web-index batch runner.

A composite batch whose sub-sources are the Marginalia Search API, the
Common Crawl CDXJ/URL index and a self-hosted SearXNG instance. The first two
are public HTTPS APIs; the third is operated inside this image (loopback only,
upstream pinned to an exact commit) because SearXNG is a self-hosted metasearch
engine rather than a public API. Every endpoint, query parameter,
authentication requirement, documented rate limit and pin was read from the
sub-source's own official documentation and is recorded in RATE_LIMITS.md next
to this file. No endpoint, parameter, crawl id or commit was inferred from an
example response.

The marginalia/common-crawl path is standard library only. The embedded
SearXNG instance is the upstream project installed from the pinned commit
(see RATE_LIMITS.md); this runner only writes its instance settings, boots the
documented webapp on 127.0.0.1 and queries the documented /search?format=json
endpoint over loopback.

--health prints exactly "ok" on stdout and returns 0 without any network access:
the sub-source inventory (kind, endpoint, whether a key is configured) is
written to stderr as one JSON line, because the Docker integration smoke case
asserts stdout.strip() == "ok". No secret value is ever printed or recorded.

--selftest-searxng boots the embedded instance on loopback (no external
network), issues one query and prints a small JSON report; it is the Docker
integration case for the self-hosted sub-source.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -- sub-sources ---------------------------------------------------------------

# Implemented sub-sources. Two are HTTPS JSON APIs; searxng is a loopback-only
# self-hosted instance operated inside this image. Each one is queried at most
# once per run.
SUPPORTED_SUB_SOURCES = (
    "marginalia",
    "common-crawl-index",
    "searxng",
)

# Dropped candidates. Google's Custom Search JSON API is closed to new
# customers, so it cannot be queried; it is reported once per run as an
# auditable skip with that exact reason, and no endpoint is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "google-custom-search": (
        'Google\'s own documentation states verbatim "The Custom Search JSON API is closed to new '
        'customers" and "This API is not available for new customers", with the service '
        "discontinuation on January 1, 2027 "
        "(https://developers.google.com/custom-search/v1/overview). A new deployment cannot register."
    ),
}

# -- documented endpoints ------------------------------------------------------
#
# Every constant below is the verbatim endpoint or value from the sub-source's
# own documentation; the docs URL for each one is recorded next to it and in
# RATE_LIMITS.md.

# Marginalia Search API. The project's own API page documents the new API at
# https://api2.marginalia-search.com and the request
# GET https://api2.marginalia-search.com/search?query=<query> with the API key in
# the API-Key request header on every request.
MARGINALIA_DOCS = "https://about.marginalia-search.com/article/api/"
MARGINALIA_API_URL = "https://api2.marginalia-search.com/search"
MARGINALIA_INVOCATION = "GET https://api2.marginalia-search.com/search?query=<query>"

# This adapter's own environment-variable name for the Marginalia key. The
# vendor does not publish an environment-variable name; the API page documents
# the key in the API-Key header and documents a public development key.
MARGINALIA_API_KEY_ENV = "MARGINALIA_API_KEY"
# The documented public key, quoted verbatim from the API page: "If you want to
# develop an integration but do not yet have a key, you can use the key public.
# Note that this key cannot create custom filters, and often hits a rate limit."
MARGINALIA_PUBLIC_KEY = "public"

# Common Crawl CDXJ/URL index. https://commoncrawl.org/get-started documents the
# index server as https://index.commoncrawl.org/, queried as
# GET /<CC-MAIN-YYYY-NN>-index?url=<url>&output=json, with the crawl id as a
# path segment.
COMMON_CRAWL_DOCS = "https://commoncrawl.org/get-started"
COMMON_CRAWL_INDEX_BASE = "https://index.commoncrawl.org"
# The crawl id is an explicit pinned crawl, never a wildcard. This is the most
# recent crawl id listed on the official crawl list at
# https://commoncrawl.org/get-started when this adapter was written; that page is
# the source of this exact id and also records it at
# https://data.commoncrawl.org/crawl-data/CC-MAIN-2026-39/index.html.
COMMON_CRAWL_CRAWL_ID = "CC-MAIN-2026-39"
COMMON_CRAWL_CRAWL_ID_SOURCE = "https://commoncrawl.org/get-started"
COMMON_CRAWL_INVOCATION = (
    "GET https://index.commoncrawl.org/<CC-MAIN-YYYY-NN>-index?url=<url>&output=json"
)

# SearXNG self-hosted instance (loopback only). SearXNG is a self-hosted
# metasearch engine, not a public API: the resolved route for it is "build as
# a self-hosted container instance (JSON endpoint enabled)". The upstream
# project is installed from the exact commit below and the runner boots the
# documented webapp locally. The JSON output format is an instance-side
# setting: the search API documentation states that supported formats are
# defined in settings.yml under `search:` and that "Requesting an unset format
# will return a 403 Forbidden error", so this runner's generated settings
# enable both html and json.
SEARXNG_DOCS = "https://docs.searxng.org/dev/search_api.html"
SEARXNG_INSTALL_DOCS = "https://docs.searxng.org/admin/installation-searxng.html"
SEARXNG_SOURCE_URL = "https://github.com/searxng/searxng"
# The exact upstream commit this image installs. It is the release the official
# project documentation builds from ("SearXNG Documentation
# (2026.10.17+1c10abe2d)") and its signature is verified in the upstream
# repository; the value was read from the project's own pages, never guessed.
SEARXNG_PINNED_COMMIT = "1c10abe2d3e4ab7ddcc4e9da1a7d07dc7ca7f8f4"
SEARXNG_LICENSE = "AGPL-3.0-or-later (operated unmodified from the pinned upstream commit)"
SEARXNG_INSTALL_DIR = "/opt/searxng"
SEARXNG_BIND_ADDRESS = "127.0.0.1"
SEARXNG_PORT = 8888
SEARXNG_BASE_URL = "http://" + SEARXNG_BIND_ADDRESS + ":" + str(SEARXNG_PORT)
SEARXNG_SEARCH_URL = SEARXNG_BASE_URL + "/search"
SEARXNG_INVOCATION = (
    "GET http://127.0.0.1:8888/search?q=<query>&format=json (loopback-only; "
    "the instance fans out to its configured engines)"
)
# The engine set is kept to keyless engines that are enabled by default in the
# pinned upstream settings; the instance-side keep_only mechanism documented at
# https://docs.searxng.org/admin/settings/settings.html restricts the default
# engine list to exactly these names.
SEARXNG_ENGINES = (
    "duckduckgo",
    "brave",
    "wikipedia",
)
SEARXNG_BOOT_TIMEOUT_SECONDS = 60
SEARXNG_QUERY_TIMEOUT_SECONDS = 45

USER_AGENT = "Aletheia/0.9.0 (search-engines)"

# One run answers a single seed. Store at most this many records per sub-source.
MAX_RECORDS = 25

# Cap any single response so a misbehaving endpoint cannot exhaust memory.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

HTTP_TIMEOUT_SECONDS = 30


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


# -- HTTP ----------------------------------------------------------------------


def _request_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,*/*"}
    if headers:
        request_headers.update(headers)
    return request_headers


def _fetch_bytes(
    url: str,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[bytes | None, int, str | None]:
    """Fetch one response body as bytes. Returns (body, http_status, error).

    Any credential is carried inside the URL or the request headers by the
    caller; neither the URL nor the headers are ever printed by this runner.
    """
    request = urllib.request.Request(url, headers=_request_headers(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            status = response.status
            if len(body) > max_bytes:
                return None, status, (
                    "Response exceeded the " + str(max_bytes // (1024 * 1024)) + " MB safety limit"
                )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, "HTTP " + str(exc.code) + ": " + detail[:500]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, type(exc).__name__ + ": " + str(exc)
    return body, status, None


def _fetch_json(
    url: str,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[Any, int, str | None]:
    """Fetch one JSON document. Returns (data, http_status, error)."""
    body, status, error = _fetch_bytes(url, timeout=timeout, headers=headers, max_bytes=max_bytes)
    if error:
        return None, status, error
    try:
        return json.loads((body or b"").decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, "JSON decode error: " + str(exc)


def _fetch_text(
    url: str,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[str | None, int, str | None]:
    """Fetch one JSON/JSONL document as text. Returns (text, http_status, error)."""
    body, status, error = _fetch_bytes(url, timeout=timeout, headers=headers, max_bytes=max_bytes)
    if error:
        return None, status, error
    return (body or b"").decode("utf-8", errors="replace"), status, None


class SourceResult:
    def __init__(
        self,
        name: str,
        data: dict | list | None = None,
        http_status: int = 0,
        error: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
    ):
        self.name = name
        self.data = data
        self.http_status = http_status
        self.error = error
        self.skipped = skipped
        self.skip_reason = skip_reason
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.raw_hash = _sha256(json.dumps(data, sort_keys=True).encode()) if data else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.name,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "timestamp": self.timestamp,
            "http_status": self.http_status,
            "error": self.error,
            "raw_hash": self.raw_hash,
            "data": self.data,
        }


def _skip(name: str, reason: str) -> SourceResult:
    """A sub-source that is deliberately not queried this run, with its reason."""
    return SourceResult(name, skipped=True, skip_reason=reason)


def _payload(
    *,
    api_source: str,
    api_documentation: str,
    endpoint: str,
    invocation: str,
    query: str,
    records: list[dict[str, Any]],
    total: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "api_source": api_source,
        "api_documentation": api_documentation,
        "endpoint": endpoint,
        "invocation": invocation,
        "query": query,
        "record_count": total,
        "truncated": total > len(records),
    }
    if extra:
        data.update(extra)
    data["records"] = records
    return data


# -- Marginalia ----------------------------------------------------------------


def query_marginalia(value: str) -> SourceResult:
    configured_key = os.environ.get(MARGINALIA_API_KEY_ENV, "").strip()
    key_source = "environment" if configured_key else "documented-public-default"
    # The API key is carried only in the API-Key request header, never in the
    # URL, so the recorded endpoint never contains a credential.
    endpoint = MARGINALIA_API_URL + "?" + urllib.parse.urlencode({"query": value})
    data, status, error = _fetch_json(endpoint, headers={"API-Key": configured_key or MARGINALIA_PUBLIC_KEY})
    if error:
        return SourceResult("marginalia", http_status=status, error=error)
    if not isinstance(data, dict):
        return SourceResult("marginalia", http_status=status, error="Unexpected response shape from Marginalia")

    results = data.get("results")
    if not isinstance(results, list) or not results:
        return SourceResult("marginalia", http_status=status)

    records: list[dict[str, Any]] = []
    for result in results[:MAX_RECORDS]:
        if not isinstance(result, dict):
            continue
        url = _clean(result.get("url"))
        title = _clean(result.get("title"))
        records.append(
            {
                "record_id": url or value,
                "detail": "Marginalia result " + (title or url),
                "title": result.get("title"),
                "url": result.get("url"),
                "snippet": result.get("description"),
            }
        )

    if not records:
        return SourceResult("marginalia", http_status=status)

    payload = _payload(
        api_source="Marginalia Search API (public search index)",
        api_documentation=MARGINALIA_DOCS,
        endpoint=endpoint,
        invocation=MARGINALIA_INVOCATION,
        query=value,
        records=records,
        total=len(results),
        extra={"license": data.get("license"), "key_source": key_source},
    )
    return SourceResult("marginalia", data=payload, http_status=status)


# -- Common Crawl CDXJ/URL index -----------------------------------------------


def _common_crawl_endpoint(value: str) -> str:
    # The crawl id is an explicit pinned path segment, never a wildcard.
    path = "/" + COMMON_CRAWL_CRAWL_ID + "-index"
    return COMMON_CRAWL_INDEX_BASE + path + "?" + urllib.parse.urlencode(
        {"url": value, "output": "json"}
    )


def query_common_crawl_index(value: str) -> SourceResult:
    endpoint = _common_crawl_endpoint(value)
    text, status, error = _fetch_text(endpoint)
    if error:
        return SourceResult("common-crawl-index", http_status=status, error=error)

    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return SourceResult("common-crawl-index", http_status=status)

    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            if not records:
                return SourceResult(
                    "common-crawl-index",
                    http_status=status,
                    error="JSON decode error in JSONL response: " + str(exc),
                )
            break
        if not isinstance(item, dict):
            continue
        if "error" in item and not records:
            return SourceResult(
                "common-crawl-index",
                http_status=status,
                error="Common Crawl index error: " + _clean(item.get("error")),
            )
        url = _clean(item.get("url"))
        # CDXJ records carry an offset for the WARC record; length/offset are the
        # documented CDX fields. Only the documented fields are recorded.
        records.append(
            {
                "record_id": url or _clean(item.get("urlkey")) or value,
                "detail": "Common Crawl "
                + COMMON_CRAWL_CRAWL_ID
                + " index record for "
                + (url or value)
                + " (status "
                + _clean(item.get("status"))
                + ")",
                "urlkey": item.get("urlkey"),
                "timestamp": item.get("timestamp"),
                "url": item.get("url"),
                "mime": item.get("mime"),
                "status": item.get("status"),
                "digest": item.get("digest"),
                "length": item.get("length"),
                "offset": item.get("offset"),
                "filename": item.get("filename"),
            }
        )
        if len(records) >= MAX_RECORDS:
            break

    if not records:
        return SourceResult("common-crawl-index", http_status=status)

    payload = _payload(
        api_source="Common Crawl CDXJ/URL index (" + COMMON_CRAWL_CRAWL_ID + ")",
        api_documentation=COMMON_CRAWL_DOCS,
        endpoint=endpoint,
        invocation=COMMON_CRAWL_INVOCATION,
        query=value,
        records=records,
        total=len(lines),
        extra={
            "crawl_id": COMMON_CRAWL_CRAWL_ID,
            "crawl_id_source": COMMON_CRAWL_CRAWL_ID_SOURCE,
        },
    )
    return SourceResult("common-crawl-index", data=payload, http_status=status)


# -- SearXNG (self-hosted, loopback only) --------------------------------------


# The generated instance settings. They rely on the documented
# use_default_settings/keep_only mechanism so the instance runs exactly the
# three keyless engines above and nothing else; secret_key is a placeholder --
# the boot sets SEARXNG_SECRET to a random value, which the settings loader
# uses to overwrite it, and no secret is ever printed or recorded.
SEARXNG_SETTINGS_SECRET_PLACEHOLDER = "aletheia-ephemeral-overridden-by-SEARXNG_SECRET"


def _searxng_settings_dict(proxy_url: str | None = None) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "use_default_settings": {"engines": {"keep_only": list(SEARXNG_ENGINES)}},
        "general": {"debug": False, "instance_name": "Aletheia local run instance"},
        "search": {"safe_search": 0, "autocomplete": "", "formats": ["html", "json"]},
        "server": {
            "secret_key": SEARXNG_SETTINGS_SECRET_PLACEHOLDER,
            "bind_address": SEARXNG_BIND_ADDRESS,
            "port": SEARXNG_PORT,
            "limiter": False,
            "image_proxy": False,
        },
        "outgoing": {"request_timeout": 8.0, "max_request_timeout": 15.0},
        "engines": [
            {"name": "duckduckgo", "disabled": False},
            {"name": "brave", "disabled": False},
            {"name": "wikipedia", "disabled": False, "display_type": ["infobox", "list"]},
        ],
    }
    if proxy_url:
        # Documented in the pinned settings file: outgoing.proxies maps URL
        # patterns to proxy URLs, so live runs route the instance's engine
        # requests through the same egress proxy as every other sub-source.
        settings["outgoing"]["proxies"] = {"all://": [proxy_url]}
    return settings


def _searxng_proxy_url() -> str | None:
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _write_searxng_settings(settings_path: Path, proxy_url: str | None) -> None:
    # JSON is a subset of YAML, so the settings loader parses this file with
    # its usual yaml.safe_load; the runner needs no YAML emitter dependency.
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(_searxng_settings_dict(proxy_url), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fetch_json_local(
    url: str, timeout: int = SEARXNG_QUERY_TIMEOUT_SECONDS
) -> tuple[Any, int, str | None]:
    """Fetch JSON from the loopback instance without any proxy handling.

    The instance's own outbound engine requests go through the generated
    outgoing.proxies setting in live runs; the request to 127.0.0.1 must never
    be proxied, so this opener disables proxy handling entirely.
    """
    request = urllib.request.Request(url, headers=_request_headers())
    try:
        with _LOCAL_OPENER.open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
            if len(body) > MAX_RESPONSE_BYTES:
                return None, status, (
                    "Response exceeded the " + str(MAX_RESPONSE_BYTES // (1024 * 1024)) + " MB safety limit"
                )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, "HTTP " + str(exc.code) + ": " + detail[:500]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, type(exc).__name__ + ": " + str(exc)
    try:
        return json.loads(body.decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, "JSON decode error: " + str(exc)


_SEARXNG_PROCESS: subprocess.Popen | None = None
_SEARXNG_LOG_PATH: Path | None = None


def _searxng_probe() -> int:
    """Return the HTTP status of the loopback instance root, or 0 if down."""
    request = urllib.request.Request(SEARXNG_BASE_URL + "/", headers=_request_headers())
    try:
        with _LOCAL_OPENER.open(request, timeout=2) as response:
            response.read(1024)
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def _searxng_log_tail(limit: int = 400) -> str:
    if _SEARXNG_LOG_PATH is None or not _SEARXNG_LOG_PATH.is_file():
        return ""
    try:
        text = _SEARXNG_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:].strip().replace("\n", " ")


def _boot_searxng() -> tuple[bool, str | None]:
    """Start the embedded instance if it is not already serving, and wait for it.

    Returns (ok, error). Never raises for a failed boot: the caller records the
    failure as this sub-source's error for the run.
    """
    global _SEARXNG_PROCESS, _SEARXNG_LOG_PATH
    if _searxng_probe():
        return True, None
    if not Path(SEARXNG_INSTALL_DIR, "searx", "webapp.py").is_file():
        return False, "the pinned SearXNG tree is missing at " + SEARXNG_INSTALL_DIR
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SEARXNG_SECRET"] = secrets.token_hex(32)
    log_dir = Path(tempfile.mkdtemp(prefix="aletheia-searxng-"))
    settings_path = log_dir / "settings.yml"
    _write_searxng_settings(settings_path, _searxng_proxy_url())
    env["SEARXNG_SETTINGS_PATH"] = str(settings_path)
    # The loopback request and the instance's own boot must never be sent to
    # the egress proxy; engine requests are routed via the generated
    # outgoing.proxies setting instead.
    no_proxy = env.get("NO_PROXY") or env.get("no_proxy") or ""
    env["NO_PROXY"] = ",".join(part for part in (no_proxy, "127.0.0.1,localhost") if part)
    webapp_log = log_dir / "webapp.log"
    _SEARXNG_LOG_PATH = webapp_log
    with open(webapp_log, "wb") as handle:
        try:
            _SEARXNG_PROCESS = subprocess.Popen(
                [sys.executable, "-m", "searx.webapp"],
                cwd=SEARXNG_INSTALL_DIR,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            return False, "the webapp could not be started: " + type(exc).__name__ + ": " + str(exc)
    deadline = time.monotonic() + SEARXNG_BOOT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _searxng_probe():
            return True, None
        if _SEARXNG_PROCESS.poll() is not None:
            return False, "the webapp exited at boot: " + _searxng_log_tail()
        time.sleep(0.5)
    return False, (
        "the webapp did not answer on loopback within "
        + str(SEARXNG_BOOT_TIMEOUT_SECONDS)
        + "s: "
        + _searxng_log_tail()
    )


def _searxng_endpoint(value: str) -> str:
    return SEARXNG_SEARCH_URL + "?" + urllib.parse.urlencode({"q": value, "format": "json"})


def _searxng_unresponsive_names(data: dict) -> list[str]:
    """Normalize the documented unresponsive_engines list to plain strings."""
    unresponsive = data.get("unresponsive_engines")
    names: list[str] = []
    if isinstance(unresponsive, list):
        for item in unresponsive:
            if isinstance(item, (list, tuple)) and item:
                engine = _clean(item[0])
                reason = _clean(item[1]) if len(item) > 1 else ""
                names.append(engine + (": " + reason if reason else ""))
            elif isinstance(item, str):
                names.append(item)
    return names[:20]


def query_searxng(value: str) -> SourceResult:
    """Query the embedded SearXNG instance over loopback (or record its error)."""
    ok, boot_error = _boot_searxng()
    if not ok:
        return SourceResult(
            "searxng", error="SearXNG instance did not start: " + (boot_error or "unknown error")
        )
    endpoint = _searxng_endpoint(value)
    data, status, error = _fetch_json_local(endpoint)
    if error:
        return SourceResult("searxng", http_status=status, error=error)
    if not isinstance(data, dict):
        return SourceResult("searxng", http_status=status, error="Unexpected response shape from SearXNG")

    results = data.get("results")
    records: list[dict[str, Any]] = []
    engines_used: list[str] = []
    if isinstance(results, list):
        for item in results[:MAX_RECORDS]:
            if not isinstance(item, dict):
                continue
            url = _clean(item.get("url"))
            if not url:
                continue
            engine = _clean(item.get("engine"))
            if engine and engine not in engines_used:
                engines_used.append(engine)
            title = _clean(item.get("title"))
            records.append(
                {
                    "record_id": url,
                    "detail": "SearXNG result " + (title or url) + (" via " + engine if engine else ""),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("content"),
                    "engine": item.get("engine"),
                }
            )

    unresponsive = _searxng_unresponsive_names(data)
    if not records:
        if unresponsive:
            return SourceResult(
                "searxng",
                http_status=status,
                error="SearXNG returned no results; unresponsive engines: " + "; ".join(unresponsive),
            )
        return SourceResult("searxng", http_status=status)

    payload = _payload(
        api_source="SearXNG (self-hosted instance, loopback only)",
        api_documentation=SEARXNG_DOCS,
        endpoint=endpoint,
        invocation=SEARXNG_INVOCATION,
        query=value,
        records=records,
        total=len(results) if isinstance(results, list) else len(records),
        extra={
            "instance": SEARXNG_BASE_URL,
            "pinned_commit": SEARXNG_PINNED_COMMIT,
            "engines_config": list(SEARXNG_ENGINES),
            "engines_used": engines_used,
            "unresponsive_engines": unresponsive,
            "number_of_results": data.get("number_of_results"),
        },
    )
    return SourceResult("searxng", data=payload, http_status=status)


def _searxng_selftest() -> int:
    """Boot the embedded instance on loopback, query once, report JSON."""
    report: dict[str, Any] = {
        "searxng_selftest": "failed",
        "pinned_commit": SEARXNG_PINNED_COMMIT,
        "instance": SEARXNG_BASE_URL,
        "engine_set": list(SEARXNG_ENGINES),
    }
    ok, boot_error = _boot_searxng()
    if not ok:
        report["error"] = boot_error
        print(json.dumps(report, sort_keys=True))
        return 1
    data, status, error = _fetch_json_local(_searxng_endpoint("aletheia docker integration selftest"))
    report["http_status"] = status
    if error:
        report["error"] = error
        print(json.dumps(report, sort_keys=True))
        return 1
    record_count = 0
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        record_count = len(data["results"])
    report.update(
        {
            "searxng_selftest": "ok",
            "results_returned": record_count,
            "unresponsive_engines": _searxng_unresponsive_names(data if isinstance(data, dict) else {}),
        }
    )
    print(json.dumps(report, sort_keys=True))
    return 0


# -- dropped candidates --------------------------------------------------------


def query_google_custom_search(value: str) -> SourceResult:
    """Never queried: the Custom Search JSON API is closed to new customers.

    The runner reports the documented reason so the candidate is an auditable
    skip rather than a silent omission, and no endpoint is invented for it.
    """
    return _skip("google-custom-search", UNSUPPORTED_SUB_SOURCES["google-custom-search"])


# -- health --------------------------------------------------------------------


def _marginalia_key_configured() -> bool:
    return bool(os.environ.get(MARGINALIA_API_KEY_ENV, "").strip())


def _health_inventory() -> dict[str, Any]:
    """Describe sub-source availability without any network call."""
    entries: list[dict[str, Any]] = [
        {
            "source": "marginalia",
            "kind": "http_api",
            "usable": True,
            "endpoint": MARGINALIA_API_URL,
            "key_env": MARGINALIA_API_KEY_ENV,
            "key_configured": _marginalia_key_configured(),
            "detail": (
                "API key in the API-Key header; falls back to the documented public key when "
                "the environment variable is unset; reachability is not tested by --health"
            ),
        },
        {
            "source": "common-crawl-index",
            "kind": "http_api",
            "usable": True,
            "endpoint": COMMON_CRAWL_INDEX_BASE + "/" + COMMON_CRAWL_CRAWL_ID + "-index",
            "key_env": None,
            "key_configured": False,
            "detail": (
                "no authentication; crawl id pinned to " + COMMON_CRAWL_CRAWL_ID + "; "
                "reachability is not tested by --health; no network request is made"
            ),
        },
        {
            "source": "searxng",
            "kind": "self_hosted_instance",
            "usable": True,
            "endpoint": SEARXNG_SEARCH_URL,
            "key_env": None,
            "key_configured": False,
            "detail": (
                "loopback-only instance embedded in this image; upstream pinned at "
                + SEARXNG_PINNED_COMMIT
                + "; engine set kept to "
                + ", ".join(SEARXNG_ENGINES)
                + "; reachability is not tested by --health; no network request is made"
            ),
        },
    ]
    for name in sorted(UNSUPPORTED_SUB_SOURCES):
        entries.append(
            {
                "source": name,
                "kind": "dropped",
                "usable": False,
                "endpoint": None,
                "key_env": None,
                "key_configured": False,
                "detail": UNSUPPORTED_SUB_SOURCES[name],
            }
        )
    return {
        "health": "ok",
        "network_used": False,
        "sub_sources": entries,
        "dropped_sub_sources": sorted(UNSUPPORTED_SUB_SOURCES),
    }


def main() -> int:
    if sys.argv[1:] == ["--selftest-searxng"]:
        return _searxng_selftest()

    if sys.argv[1:] == ["--health"]:
        # stdout must stay exactly "ok" (the Docker integration case asserts
        # stdout.strip() == "ok"), so the inventory goes to stderr.
        print(json.dumps(_health_inventory(), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        print("ok")
        return 0

    if len(sys.argv) < 3:
        print("usage: runner.py <input_type> <value>", file=sys.stderr)
        print("input_type: name", file=sys.stderr)
        return 2

    input_type = sys.argv[1]
    value = sys.argv[2]

    valid_types = {"name"}
    if input_type not in valid_types:
        print(
            "Invalid input_type: " + input_type + ". Must be one of: " + str(sorted(valid_types)),
            file=sys.stderr,
        )
        return 2

    # Every candidate sub-source is reported once per run. The dropped candidates
    # are reported as documented skips and are never queried.
    results = [
        query_marginalia(value),
        query_common_crawl_index(value),
        query_searxng(value),
        query_google_custom_search(value),
    ]

    output = {
        "input_type": input_type,
        "input_value": value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [result.to_dict() for result in results],
    }

    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
