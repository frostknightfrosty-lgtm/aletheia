"""Code search batch runner.

A composite batch whose only implemented sub-source is the Debian Code Search
JSON API. Every endpoint, query parameter, authentication requirement,
documented rate limit and documentation URL was read from the project's own
OpenAPI specification (https://codesearch.debian.net/openapi.json) and its own
API-key FAQ, and is recorded in RATE_LIMITS.md next to this file. No endpoint,
parameter name or version was inferred from an example response.

The verified contract did not include the OpenAPI response schema, so this
runner records the parsed JSON document verbatim instead of assuming field
names, and the adapter normalizes one record per sub-source from it.

Standard library only (urllib, json, hashlib, os, sys): the image installs no
third-party Python package.

--health prints exactly "ok" on stdout and returns 0 without any network access:
the sub-source inventory (kind, endpoint, whether the required key is
configured) is written to stderr as one JSON line, because the Docker
integration smoke case asserts stdout.strip() == "ok". No secret value is ever
printed or recorded.
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

# Implemented sub-sources. Debian Code Search is an HTTPS JSON API queried at
# most once per run.
SUPPORTED_SUB_SOURCES = (
    "debian-code-search",
)

# Dropped candidates. Neither can be used: GitLab's Search API requires
# authentication for every call and PublicWWW's API is paid-only. Each is
# reported once per run as an auditable skip with the exact documented reason
# and is never queried; no endpoint is invented for either.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "gitlab-search": (
        'GitLab\'s own Search API docs state verbatim "Every call to this API requires authentication." '
        "(https://docs.gitlab.com/api/search/), and a live probe of "
        "GET https://gitlab.com/api/v4/search?scope=blobs&search=test returned HTTP 401. "
        "The code-search scope therefore cannot be used without a token, and no token flow is implemented."
    ),
    "publicwww": (
        'PublicWWW\'s own API authentication docs state verbatim "A paid plan is required: without one, '
        'every endpoint except / and /v1/account answers 403 plan_required." '
        "(https://publicwww.com/docs/api/authentication/). A paid-only source is barred by standing rule 4, "
        "so it is not implemented. (Its documented base URL is https://api.publicwww.com with an "
        "Authorization: Bearer header, recorded for context only.)"
    ),
}

# -- documented endpoint -------------------------------------------------------
#
# Every constant below is the verbatim endpoint from the project's own OpenAPI
# specification; its docs URL is recorded next to it and in RATE_LIMITS.md.

# Debian Code Search. The specification's server is
# https://codesearch.debian.net/api/v1 and it documents GET /search with query
# parameters query (required) and match_mode (optional); GET /searchperpackage
# takes the same parameters and is not used.
DEBIAN_CODE_SEARCH_DOCS = "https://codesearch.debian.net/"
DEBIAN_CODE_SEARCH_OPENAPI = "https://codesearch.debian.net/openapi.json"
DEBIAN_CODE_SEARCH_API_BASE = "https://codesearch.debian.net/api/v1"
DEBIAN_CODE_SEARCH_SEARCH_URL = DEBIAN_CODE_SEARCH_API_BASE + "/search"

# This adapter's own environment-variable name. The vendor does not publish an
# environment-variable name; the specification defines the credential as an API
# key sent in the x-dcs-apikey HTTP header, and this name is mapped to it.
DEBIAN_CODE_SEARCH_API_KEY_ENV = "DEBIAN_CODE_SEARCH_API_KEY"

# Documented invocation of the implemented sub-source, from its specification.
DEBIAN_CODE_SEARCH_INVOCATION = (
    "GET https://codesearch.debian.net/api/v1/search?query=<query> "
    "(optional match_mode=<match_mode>)"
)

USER_AGENT = "Aletheia/0.9.0 (code-search)"

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


def _fetch_json(
    url: str,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[Any, int, str | None]:
    """Fetch one JSON document. Returns (data, http_status, error).

    The API key is carried in the request headers by the caller; neither the URL
    nor the headers are ever printed by this runner.
    """
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,*/*"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
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
    try:
        return json.loads(body.decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, "JSON decode error: " + str(exc)


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


# -- Debian Code Search --------------------------------------------------------


def query_debian_code_search(value: str) -> SourceResult:
    api_key = os.environ.get(DEBIAN_CODE_SEARCH_API_KEY_ENV, "").strip()
    if not api_key:
        return _skip(
            "debian-code-search",
            "DEBIAN_CODE_SEARCH_API_KEY is not set. The Debian Code Search OpenAPI specification "
            "(https://codesearch.debian.net/openapi.json) defines the credential as an API key in the "
            "required x-dcs-apikey HTTP header, and a keyless request is answered HTTP 403, so the "
            "sub-source is not queried.",
        )

    # query is required; match_mode is optional and is not sent, so the service
    # default applies. The key travels in a header and never in the URL.
    endpoint = DEBIAN_CODE_SEARCH_SEARCH_URL + "?" + urllib.parse.urlencode({"query": value})
    data, status, error = _fetch_json(endpoint, headers={"x-dcs-apikey": api_key})
    if error:
        return SourceResult("debian-code-search", http_status=status, error=error)
    if data is None:
        return SourceResult("debian-code-search", http_status=status)

    if isinstance(data, list):
        response_type = "array"
    elif isinstance(data, dict):
        response_type = "object"
    else:
        response_type = type(data).__name__

    record = {
        "record_id": value,
        "detail": (
            "Debian Code Search response document for query '"
            + value
            + "' recorded verbatim ("
            + response_type
            + "); the OpenAPI response schema was not part of the verified contract, so no field name is assumed."
        ),
        "response_type": response_type,
    }

    payload: dict[str, Any] = {
        "api_source": "Debian Code Search (GET /api/v1/search)",
        "api_documentation": DEBIAN_CODE_SEARCH_DOCS,
        "openapi_specification": DEBIAN_CODE_SEARCH_OPENAPI,
        "endpoint": endpoint,
        "invocation": DEBIAN_CODE_SEARCH_INVOCATION,
        "query": value,
        "match_mode": None,
        "record_count": 1,
        "records": [record],
        "response": data,
        "truncated": False,
    }
    return SourceResult("debian-code-search", data=payload, http_status=status)


# -- dropped candidates --------------------------------------------------------


def query_gitlab_search(value: str) -> SourceResult:
    """Never queried: every GitLab Search API call requires authentication.

    The runner reports the documented reason so the candidate is an auditable
    skip rather than a silent omission, and no endpoint is invented for it.
    """
    return _skip("gitlab-search", UNSUPPORTED_SUB_SOURCES["gitlab-search"])


def query_publicwww(value: str) -> SourceResult:
    """Never queried: PublicWWW's API is paid-only.

    The runner reports the documented reason so the candidate is an auditable
    skip rather than a silent omission, and no endpoint is invented for it.
    """
    return _skip("publicwww", UNSUPPORTED_SUB_SOURCES["publicwww"])


# -- health --------------------------------------------------------------------


def _health_inventory() -> dict[str, Any]:
    """Describe sub-source availability without any network call."""
    entries: list[dict[str, Any]] = []
    for name, endpoint, credential_env in (
        ("debian-code-search", DEBIAN_CODE_SEARCH_SEARCH_URL, DEBIAN_CODE_SEARCH_API_KEY_ENV),
    ):
        entries.append(
            {
                "source": name,
                "kind": "http_api",
                "usable": True,
                "endpoint": endpoint,
                "credential_env": credential_env,
                "credential_configured": bool(os.environ.get(credential_env, "").strip()),
                "detail": "reachability is not tested by --health; no network request is made",
            }
        )
    for name in sorted(UNSUPPORTED_SUB_SOURCES):
        entries.append(
            {
                "source": name,
                "kind": "dropped",
                "usable": False,
                "endpoint": None,
                "credential_env": None,
                "credential_configured": None,
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
        query_debian_code_search(value),
        query_gitlab_search(value),
        query_publicwww(value),
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
