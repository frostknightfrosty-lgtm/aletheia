"""Leak-checker composite runner.

This runner uses the documented LeakIX search API and GrayhatWarfare API v2.
Other planned sources are emitted as explicit skips with the review evidence and
integration limitations recorded in docker/leak_checkers/RATE_LIMITS.md.
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

SUPPORTED_SUB_SOURCES = ("leakix", "grayhatwarfare")
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "breachdirectory": (
        "The official BreachDirectory site (https://breachdirectory.org/) returned HTTP 403 during "
        "contract review, and no first-party endpoint, parameter, or response contract could be verified. "
        "This source is not queried until its vendor contract can be reviewed; no route is inferred."
    ),
    "leak-lookup": (
        "Leak-Lookup's Terms of Service limit use to personal security/research and searches for oneself "
        "or people authorized in writing. This adapter request model cannot verify that written "
        "authorization, so the source is not queried. See https://leak-lookup.com/support/terms#use-of-service"
    ),
    "bron-vault": (
        "Broń Vault is a self-hosted application: its README describes deploying its Docker services, "
        "uploading local log archives, and using API-key-authenticated local REST routes; it warns not "
        "to expose the app to public networks. This adapter does not deploy or upload into a separate "
        "operator-owned instance. See https://github.com/ITSEC-Research/bron-vault"
    ),
}

LEAKIX_DOCS = "https://docs.leakix.net/docs/api/search/"
LEAKIX_API_URL = "https://leakix.net/search"
LEAKIX_API_KEY_ENV = "LEAKIX_API_KEY"

GRAYHATWARFARE_DOCS = "https://buckets.grayhatwarfare.com/docs/api/v2"
GRAYHATWARFARE_FILES_URL = "https://buckets.grayhatwarfare.com/api/v2/files"
GRAYHATWARFARE_TOKEN_ENV = "GRAYHATWARFARE_TOKEN"

USER_AGENT = "Aletheia/0.9.0 (leak-checkers)"
HTTP_TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class SourceResult:
    def __init__(
        self,
        name: str,
        data: dict[str, Any] | None = None,
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
        self.raw_hash = None
        if data is not None:
            self.raw_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

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


def _request_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,*/*"}
    if headers:
        request_headers.update(headers)
    return request_headers


def _fetch_bytes(url: str, headers: dict[str, str] | None = None) -> tuple[bytes | None, int, str | None]:
    request = urllib.request.Request(url, headers=_request_headers(headers))
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
            if len(body) > MAX_RESPONSE_BYTES:
                return None, status, "Response exceeded safety limit"
            return body, status, None
    except urllib.error.HTTPError as exc:
        return None, exc.code, "HTTP status " + str(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, type(exc).__name__


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> tuple[Any, int, str | None]:
    body, status, error = _fetch_bytes(url, headers=headers)
    if error:
        return None, status, error
    try:
        return json.loads((body or b"").decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, "JSON decode error: " + str(exc)


def _skip(name: str, reason: str) -> SourceResult:
    return SourceResult(name, skipped=True, skip_reason=reason)


def _payload(
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


def query_leakix(value: str) -> SourceResult:
    key = os.environ.get(LEAKIX_API_KEY_ENV, "").strip()
    if not key:
        return _skip(
            "leakix",
            "LeakIX requires a free registered API key. The environment variable LEAKIX_API_KEY is not set, "
            "so the runner does not probe without the documented registration flow.",
        )

    query = urllib.parse.urlencode({"scope": "leak", "q": value, "page": "0"})
    endpoint = f"{LEAKIX_API_URL}?{query}"
    headers = {"Accept": "application/json", "api-key": key}
    payload, status, error = _fetch_json(endpoint, headers=headers)
    if error:
        return SourceResult("leakix", http_status=status, error=error)
    if not isinstance(payload, list):
        return SourceResult("leakix", http_status=status, error="Unexpected JSON root type")

    records: list[dict[str, Any]] = []
    for item in payload[:25]:
        if isinstance(item, dict):
            records.append({
                "record_id": item.get("event_fingerprint"),
                "subject": item.get("host") or item.get("ip"),
                "title": item.get("event_source"),
                "event_type": item.get("event_type"),
                "event_source": item.get("event_source"),
                "event_fingerprint": item.get("event_fingerprint"),
                "host": item.get("host"),
                "ip": item.get("ip"),
                "port": item.get("port"),
                "time": item.get("time"),
                "leak": _safe_leak_summary(item.get("leak")),
            })
    return SourceResult(
        "leakix",
        data=_payload(
            "LeakIX Search API",
            LEAKIX_DOCS,
            endpoint,
            f"GET {endpoint}",
            value,
            records,
            len(payload),
            extra={"key_source": "env:LEAKIX_API_KEY", "scope": "leak", "page": 0},
        ),
        http_status=status,
    )


def query_grayhatwarfare(value: str) -> SourceResult:
    token = os.environ.get(GRAYHATWARFARE_TOKEN_ENV, "").strip()
    if not token:
        return _skip(
            "grayhatwarfare",
            "GrayhatWarfare requires a free access token granted on signup; the environment variable "
            "GRAYHATWARFARE_TOKEN is not set, so the runner does not probe without the documented auth flow.",
        )

    params = urllib.parse.urlencode({"keywords": value, "limit": "25", "start": "0"})
    endpoint = f"{GRAYHATWARFARE_FILES_URL}?{params}"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    payload, status, error = _fetch_json(endpoint, headers=headers)
    if error:
        return SourceResult("grayhatwarfare", http_status=status, error=error)
    if not isinstance(payload, dict):
        return SourceResult("grayhatwarfare", http_status=status, error="Unexpected JSON root type")

    records: list[dict[str, Any]] = []
    items = payload.get("files") if isinstance(payload.get("files"), list) else []
    for item in items[:25]:
        if isinstance(item, dict):
            records.append({
                "record_id": item.get("id"),
                "subject": item.get("bucket"),
                "title": item.get("filename"),
                "bucket": item.get("bucket"),
                "filename": item.get("filename"),
                "full_path": item.get("fullPath"),
                "url": item.get("url"),
                "size": item.get("size"),
                "type": item.get("type"),
                "last_modified": item.get("lastModified"),
            })
    return SourceResult(
        "grayhatwarfare",
        data=_payload(
            "GrayhatWarfare Public Buckets API",
            GRAYHATWARFARE_DOCS,
            endpoint,
            f"GET {endpoint}",
            value,
            records,
            payload.get("meta", {}).get("results", len(items)) if isinstance(payload.get("meta"), dict) else len(items),
            extra={"key_source": "env:GRAYHATWARFARE_TOKEN"},
        ),
        http_status=status,
    )


def _run_for_input(input_type: str, value: str) -> list[dict[str, Any]]:
    sources = [query_leakix(value), query_grayhatwarfare(value)]
    sources.extend(_skip(name, reason) for name, reason in UNSUPPORTED_SUB_SOURCES.items())
    return [source.to_dict() for source in sources]


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "--health":
        inventory = [
            {"source": name, "documented": True, "key_required": True}
            for name in SUPPORTED_SUB_SOURCES
        ]
        print("ok")
        print(json.dumps({"inventory": inventory}), file=sys.stderr)
        return 0

    if len(argv) < 3:
        print("usage: runner.py <input_type> <value>", file=sys.stderr)
        return 2

    input_type = argv[1]
    value = argv[2]
    payload = {"input_type": input_type, "input_value": value, "sources": _run_for_input(input_type, value)}
    print(json.dumps(payload))
    return 0


def _safe_leak_summary(value: Any) -> dict[str, Any] | None:
    """Keep only non-secret LeakIX classification/count fields in evidence."""
    if not isinstance(value, dict):
        return None
    dataset = value.get("dataset")
    safe_dataset = None
    if isinstance(dataset, dict):
        safe_dataset = {
            key: dataset.get(key)
            for key in ("rows", "files", "size", "collections", "infected")
            if key in dataset
        }
    return {
        key: value.get(key)
        for key in ("stage", "type", "severity")
        if key in value
    } | ({"dataset": safe_dataset} if safe_dataset is not None else {})


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
