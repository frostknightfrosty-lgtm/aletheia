"""Search-engine and web-index batch runner.

A composite batch whose sub-sources are the Marginalia Search API and the
Common Crawl CDXJ/URL index, both public HTTPS APIs. Every endpoint, query
parameter, authentication requirement, documented rate limit and documentation
URL was read from the sub-source's own official documentation and is recorded in
RATE_LIMITS.md next to this file. No endpoint, parameter or crawl id was
inferred from an example response.

Standard library only (urllib, json, hashlib, os, sys): the image installs no
third-party Python package.

--health prints exactly "ok" on stdout and returns 0 without any network access:
the sub-source inventory (kind, endpoint, whether a key is configured) is
written to stderr as one JSON line, because the Docker integration smoke case
asserts stdout.strip() == "ok". No secret value is ever printed or recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

# -- sub-sources ---------------------------------------------------------------

# Implemented sub-sources. Both are HTTPS JSON APIs; each one is queried at most
# once per run.
SUPPORTED_SUB_SOURCES = (
    "marginalia",
    "common-crawl-index",
)

# Dropped candidates. Neither can be queried from this runner: searxng is a
# self-hosted metasearch engine whose JSON output is an instance-side setting,
# and Google's Custom Search JSON API is closed to new customers. Each is
# reported once per run as an auditable skip with that exact reason, and no
# endpoint is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "searxng": (
        "SearXNG is a self-hosted metasearch engine, not a public API. Its JSON output is an "
        "instance-side configuration (the search.formats setting documented at "
        "https://docs.searxng.org/dev/search_api.html) that public instances typically disable, "
        "and the brief forbids the runner from operating a self-hosted instance. No public "
        "instance with verifiable structured output is used."
    ),
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


# -- dropped candidates --------------------------------------------------------


def query_searxng(value: str) -> SourceResult:
    """Never queried: SearXNG is a self-hosted metasearch engine, not a public API.

    The runner reports the documented reason so the candidate is an auditable
    skip rather than a silent omission, and no endpoint is invented for it.
    """
    return _skip("searxng", UNSUPPORTED_SUB_SOURCES["searxng"])


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
