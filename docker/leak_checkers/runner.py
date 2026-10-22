"""Leak-checker composite runner.

This runner uses the documented LeakIX search API, the GrayhatWarfare API v2,
and the documented API v1 of a locally running Broń Vault instance (loopback
only, never public networks; see docker/leak_checkers/RATE_LIMITS.md). The
remaining candidates are emitted as explicit skips with the review evidence
and integration limitations recorded in the same file.
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

SUPPORTED_SUB_SOURCES = ("leakix", "grayhatwarfare", "bron-vault")
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
}

LEAKIX_DOCS = "https://docs.leakix.net/docs/api/search/"
LEAKIX_API_URL = "https://leakix.net/search"
LEAKIX_API_KEY_ENV = "LEAKIX_API_KEY"

GRAYHATWARFARE_DOCS = "https://buckets.grayhatwarfare.com/docs/api/v2"
GRAYHATWARFARE_FILES_URL = "https://buckets.grayhatwarfare.com/api/v2/files"
GRAYHATWARFARE_TOKEN_ENV = "GRAYHATWARFARE_TOKEN"

BRON_VAULT_DOCS = "https://github.com/ITSEC-Research/bron-vault"
# Pinned source of the API contract: release v1.4.0 of the project. The route
# files under app/api/v1/search/ in that release define the method, request
# body, auth header (X-API-Key) and response envelope this runner follows.
BRON_VAULT_VERSION_PIN = "v1.4.0 (commit 6bfdcc0196ac90ed38a35a1099697497680c1666)"
BRON_VAULT_URL_ENV = "BRON_VAULT_URL"
BRON_VAULT_API_KEY_ENV = "BRON_VAULT_API_KEY"
BRON_VAULT_SEARCH_PATH = "/api/v1/search/credentials"
# This sub-source only ever talks to a local instance. Loopback names, any
# 127.0.0.0/8 address, and Docker's documented alias for the local machine are
# accepted; anything else is refused before a socket is opened.
BRON_VAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal")

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
    if status == 204:
        # LeakIX uses 204 for a successful query with no matching records.
        # There is no body to decode; callers map None to their empty shape.
        return None, status, None
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
    if payload is None and status == 204:
        payload = []
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
    if payload is None and status == 204:
        payload = {}
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


# -- Broń Vault (operator-run local instance) ----------------------------------
#
# Broń Vault's only documented interface is the API v1 served by a locally
# running instance (its README: "REST API with API-key auth for search, lookup,
# and upload"; the README paragraph names "GET /api/v1/search/credentials", but
# the route file shipped in the pinned release implements POST - this runner
# follows the route file, and the discrepancy is recorded in
# docker/leak_checkers/RATE_LIMITS.md). The instance is operated by the user:
# this sub-source never deploys, uploads to, or configures it, and it only ever
# sends a search request to a loopback address. When no local instance is
# configured, the source reports the documented skip.


class _NoOffHostRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects that would leave the local instance."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        if not _host_allowed(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _host_allowed(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host in BRON_VAULT_ALLOWED_HOSTS or host.startswith("127.") or host.endswith(".localhost")


def _bron_vault_refusal(base_url: str) -> str | None:
    """Return the reason a configured instance URL is refused, or None."""
    try:
        parsed = urllib.parse.urlsplit(base_url)
    except ValueError:
        return "the URL could not be parsed"
    if parsed.scheme not in ("http", "https"):
        return "the URL scheme must be http or https"
    if not _host_allowed(base_url):
        return (
            "host '" + (parsed.hostname or "") + "' is not loopback; this sub-source only queries a "
            "local instance and never sends traffic off the operator's machine"
        )
    return None


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[Any, int, str | None]:
    """POST a JSON body with no proxy and no off-host redirects (loopback only)."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers=_request_headers({"Content-Type": "application/json", **headers}),
        method="POST",
    )
    # ProxyHandler({}) bypasses any proxy environment variables: a local
    # instance is never reached through the egress proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoOffHostRedirect())
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            if not _host_allowed(response.geturl()):
                return None, response.status, "redirect left the local instance"
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return None, response.status, "Response exceeded safety limit"
            try:
                return json.loads(raw.decode("utf-8", errors="replace")), response.status, None
            except json.JSONDecodeError as exc:
                return None, response.status, "JSON decode error: " + str(exc)
    except urllib.error.HTTPError as exc:
        return None, exc.code, "HTTP status " + str(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, type(exc).__name__


def query_bron_vault(value: str, input_type: str = "keyword") -> SourceResult:
    base_url = os.environ.get(BRON_VAULT_URL_ENV, "").strip().rstrip("/")
    api_key = os.environ.get(BRON_VAULT_API_KEY_ENV, "").strip()
    if not base_url or not api_key:
        return _skip(
            "bron-vault",
            "Broń Vault is a self-hosted application; this runner only queries an instance the operator "
            "already runs and never deploys, uploads to, or exposes one. Set BRON_VAULT_URL (a loopback "
            "address, e.g. http://127.0.0.1:3000) and BRON_VAULT_API_KEY (created on that instance's API "
            "Keys page) to activate this source. See https://github.com/ITSEC-Research/bron-vault",
        )
    refusal = _bron_vault_refusal(base_url)
    if refusal:
        return SourceResult("bron-vault", error="BRON_VAULT_URL refused: " + refusal)

    search_type = {"email": "email", "username": "username"}.get(input_type, "any")
    endpoint = base_url + BRON_VAULT_SEARCH_PATH
    # includePasswords stays False: the runner never requests full passwords.
    body = {"query": value, "type": search_type, "page": 1, "limit": 25, "includePasswords": False}
    payload, status, error = _post_json(endpoint, body, {"X-API-Key": api_key})
    if error:
        return SourceResult("bron-vault", http_status=status, error=error)
    if not isinstance(payload, dict):
        return SourceResult("bron-vault", http_status=status, error="Unexpected JSON root type")

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    credentials = data.get("credentials") if isinstance(data.get("credentials"), list) else []
    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

    records: list[dict[str, Any]] = []
    for item in credentials[:25]:
        if not isinstance(item, dict):
            continue
        host_info = item.get("hostInfo") if isinstance(item.get("hostInfo"), dict) else {}
        device_id = item.get("deviceId")
        domain = item.get("domain") or item.get("url")
        username = item.get("username")
        records.append({
            "record_id": f"{device_id}/{domain}",
            "detail": (
                f"{host_info.get('stealerType') or 'stealer'} log credential for "
                f"{username or 'unknown'} on {domain or 'unknown'} (password masked; full passwords are "
                "never requested)"
            ),
            "title": item.get("deviceName") or device_id,
            "url": item.get("url"),
            "device_id": device_id,
            "device_name": item.get("deviceName"),
            "domain": item.get("domain"),
            "username": username,
            "password_masked": item.get("passwordMasked"),
            "browser": item.get("browser"),
            "country": item.get("country"),
            "upload_date": item.get("uploadDate"),
            "stealer_type": host_info.get("stealerType"),
            "log_date": host_info.get("logDate"),
            "os": host_info.get("os"),
            "machine_username": host_info.get("machineUsername"),
            "hwid": host_info.get("hwid"),
            "ip_address": host_info.get("ipAddress"),
        })
    total = pagination.get("total") if isinstance(pagination.get("total"), int) else len(records)
    extra = {
        "instance_url": base_url,
        "key_source": "env:BRON_VAULT_API_KEY",
        "api_version_pin": BRON_VAULT_VERSION_PIN,
        "search_type": search_type,
        "include_passwords": False,
        "pagination": pagination,
        "searched_at": meta.get("searchedAt"),
    }
    extra = {key: value for key, value in extra.items() if value not in (None, "", [], {})}
    return SourceResult(
        "bron-vault",
        data=_payload(
            "Broń Vault API v1 (search/credentials)",
            BRON_VAULT_DOCS,
            endpoint,
            f"POST {endpoint}",
            value,
            records,
            total,
            extra=extra,
        ),
        http_status=status,
    )


def _bron_vault_selftest() -> dict[str, Any]:
    """Exercise the Bron Vault client path against a loopback stub.

    The stub implements exactly the documented v1.4.0 route contract
    (POST /api/v1/search/credentials, X-API-Key auth, the success/data envelope
    with data.credentials and data.pagination) and proves, without any off-host
    traffic: the auth header is sent, a success envelope is parsed into a
    record, a 401 is reported as an error, and a non-loopback instance URL is
    refused before any socket opens. The report never claims the real
    application ran: the real instance is operator-run and this image neither
    deploys nor starts it.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    report: dict[str, Any] = {
        "bron_vault_selftest": "failed",
        "api_version_pin": BRON_VAULT_VERSION_PIN,
        "stub_contract": "POST " + BRON_VAULT_SEARCH_PATH,
    }
    seen: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            if self.path != BRON_VAULT_SEARCH_PATH:
                self.send_response(404)
                self.end_headers()
                return
            if self.headers.get("X-API-Key") != "bv_selftest_key":
                raw = json.dumps(
                    {"success": False, "error": "Invalid API key", "code": "UNAUTHORIZED"}
                ).encode()
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            seen["request_body"] = body
            raw = json.dumps({
                "success": True,
                "data": {
                    "credentials": [{
                        "deviceId": "selftest-device",
                        "deviceName": "selftest-host",
                        "url": "https://example.invalid/login",
                        "domain": "example.invalid",
                        "username": body.get("query", ""),
                        "passwordMasked": "se***st",
                        "browser": "Chrome",
                        "country": "US",
                        "uploadDate": "2026-10-18T00:00:00Z",
                        "hostInfo": {
                            "os": "Synthetic OS",
                            "stealerType": "RedLine",
                            "logDate": "2026-10-01",
                        },
                    }],
                    "pagination": {"page": 1, "limit": 25, "total": 1, "totalPages": 1, "hasMore": False},
                },
                "meta": {
                    "query": body.get("query", ""),
                    "type": body.get("type"),
                    "searchedAt": "2026-10-18T00:00:00Z",
                },
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    previous_url = os.environ.get(BRON_VAULT_URL_ENV)
    previous_key = os.environ.get(BRON_VAULT_API_KEY_ENV)
    try:
        os.environ[BRON_VAULT_URL_ENV] = "http://127.0.0.1:" + str(server.server_address[1])
        os.environ[BRON_VAULT_API_KEY_ENV] = "bv_selftest_key"
        result = query_bron_vault("selftest@example.invalid", "email")

        os.environ[BRON_VAULT_API_KEY_ENV] = "bv_wrong_key"
        unauthorized = query_bron_vault("selftest@example.invalid", "email")

        os.environ[BRON_VAULT_API_KEY_ENV] = "bv_selftest_key"
        os.environ[BRON_VAULT_URL_ENV] = "https://example.com"
        refused = query_bron_vault("selftest@example.invalid", "email")
    finally:
        server.shutdown()
        server.server_close()
        if previous_url is None:
            os.environ.pop(BRON_VAULT_URL_ENV, None)
        else:
            os.environ[BRON_VAULT_URL_ENV] = previous_url
        if previous_key is None:
            os.environ.pop(BRON_VAULT_API_KEY_ENV, None)
        else:
            os.environ[BRON_VAULT_API_KEY_ENV] = previous_key

    if result.error:
        report["error"] = result.error
        return report
    if unauthorized.error != "HTTP status 401":
        report["error"] = "unauthorized request was not refused: " + str(unauthorized.error)
        return report
    if not refused.error or "refused" not in refused.error:
        report["error"] = "non-loopback instance URL was not refused"
        return report
    data = result.data or {}
    records = data.get("records") or []
    report["bron_vault_selftest"] = "ok"
    report["auth_header_verified"] = True
    report["unauthorized_refused"] = True
    report["non_loopback_refused"] = True
    report["search_type_sent"] = seen.get("request_body", {}).get("type")
    report["include_passwords"] = seen.get("request_body", {}).get("includePasswords")
    report["records_parsed"] = len(records)
    report["record_id"] = records[0].get("record_id") if records else None
    report["password_masked_only"] = bool(records) and "password" not in records[0]
    return report


def _run_for_input(input_type: str, value: str) -> list[dict[str, Any]]:
    sources = [
        query_leakix(value),
        query_grayhatwarfare(value),
        query_bron_vault(value, input_type),
    ]
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

    if len(argv) == 2 and argv[1] == "--selftest-bron-vault":
        report = _bron_vault_selftest()
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report.get("bron_vault_selftest") == "ok" else 1

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
