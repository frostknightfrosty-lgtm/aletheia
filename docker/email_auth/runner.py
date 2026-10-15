"""Email authentication batch runner.

A composite batch whose sub-sources are the keyless scan.mx email-authentication
HTTPS JSON API and the checkdmarc Python library, which queries DNS directly.
Every endpoint, query parameter, module, entry point, version pin and
documented rate limit was read from the sub-source's own official documentation
(https://api.scan.mx/ and https://domainaware.github.io/checkdmarc/api.html) and
is recorded in RATE_LIMITS.md next to this file. No endpoint, parameter name,
function name or version was inferred from an example response.

Standard library only except for checkdmarc, which the image installs from a
pinned PyPI release. The checkdmarc import is lazy and lives inside
query_checkdmarc, so --health runs without the package and without network
access.

--health prints exactly "ok" on stdout and returns 0 without any network access:
the sub-source inventory (kind, endpoint or module, and whether the sub-source
is usable) is written to stderr as one JSON line, because the Docker integration
smoke case asserts stdout.strip() == "ok". No secret value is ever printed or
recorded (neither sub-source needs a credential).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

# -- sub-sources ---------------------------------------------------------------

# Implemented sub-sources. scan-mx is an HTTPS JSON API queried at most once per
# run; checkdmarc is a locally installed library called once per run.
SUPPORTED_SUB_SOURCES = (
    "scan-mx",
    "checkdmarc",
)

# Dropped candidates never queried. Both candidates for this batch were verified
# from their own documentation, so this map is empty; any entry added here is
# reported once per run as an auditable skip carrying that exact reason and no
# endpoint, import or version is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {}

# -- documented endpoints and entry points -------------------------------------

# scan.mx email-authentication API. Its own API page documents the full graded
# report as GET https://api.scan.mx/v1/check?domain=example.com with no API key,
# no authentication and no signup, and the live SMTP probe stream as GET
# https://api.scan.mx/v1/check/stream?domain=example.com (this adapter does not
# use the stream endpoint).
SCAN_MX_DOCS = "https://api.scan.mx/"
SCAN_MX_CHECK_URL = "https://api.scan.mx/v1/check"
SCAN_MX_INVOCATION = "GET https://api.scan.mx/v1/check?domain=<domain>"

# checkdmarc. Its own API reference documents the importable library surface:
# checkdmarc.check_domains(domains, ...) returns a DomainCheckResult (or a list
# of them) whose keys include mx, spf and dmarc. The image pins the PyPI release
# recorded here.
CHECKDMARC_DOCS = "https://domainaware.github.io/checkdmarc/api.html"
CHECKDMARC_PYPI = "https://pypi.org/project/checkdmarc/"
CHECKDMARC_MODULE = "checkdmarc"
CHECKDMARC_ENTRY_POINT = "checkdmarc.check_domains"
CHECKDMARC_VERSION = "6.0.4"
CHECKDMARC_INVOCATION = "python: checkdmarc.check_domains([domain])"

USER_AGENT = "Aletheia/0.9.0 (email-auth)"

# One run answers a single seed. Store at most this many records/checks.
MAX_RECORDS = 25
MAX_CHECKS = 50

# Cap any single response so a misbehaving endpoint cannot exhaust memory.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

HTTP_TIMEOUT_SECONDS = 30

# A fully qualified domain name, which is what both sub-sources document.
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _domain(value: str) -> str:
    """Return the lowercased value when it is a fully qualified domain name."""
    text = _clean(value).lower()
    return text if DOMAIN_RE.match(text) else ""


# -- HTTP ----------------------------------------------------------------------


def _fetch_json(
    url: str,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[Any, int, str | None]:
    """Fetch one JSON document. Returns (data, http_status, error)."""
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


def _payload(
    *,
    api_source: str,
    api_documentation: str,
    query: str,
    records: list[dict[str, Any]],
    total: int,
    endpoint: str | None = None,
    module: str | None = None,
    invocation: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "api_source": api_source,
        "api_documentation": api_documentation,
        "query": query,
        "record_count": total,
        "truncated": total > len(records),
    }
    if endpoint is not None:
        data["endpoint"] = endpoint
    if module is not None:
        data["module"] = module
    if invocation is not None:
        data["invocation"] = invocation
    if extra:
        data.update(extra)
    data["records"] = records
    return data


# -- scan.mx -------------------------------------------------------------------


def query_scan_mx(value: str) -> SourceResult:
    domain = _domain(value)
    if not domain:
        return _skip(
            "scan-mx",
            "The scan.mx check endpoint documents a fully qualified domain name in its domain query "
            "parameter and answers HTTP 422 invalid_domain for anything else, so the supplied value is "
            "not sent.",
        )
    # The endpoint is documented verbatim as /v1/check?domain=; the domain is
    # quoted as a single query parameter value.
    endpoint = SCAN_MX_CHECK_URL + "?" + urllib.parse.urlencode({"domain": domain})
    data, status, error = _fetch_json(endpoint)
    if error:
        return SourceResult("scan-mx", http_status=status, error=error)
    if not isinstance(data, dict) or not _clean(data.get("domain")):
        return SourceResult("scan-mx", http_status=status, error="Unexpected response shape from scan.mx")

    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    grade = _clean(data.get("grade"))
    record = {
        "record_id": _clean(data.get("domain")) or domain,
        "detail": (
            "scan.mx email-authentication report for "
            + domain
            + ": grade "
            + (grade or "unknown")
            + " (score "
            + _clean(data.get("score"))
            + ")"
        ),
        "domain": _clean(data.get("domain")) or domain,
        "grade": data.get("grade"),
        "score": data.get("score"),
        "provider": data.get("provider"),
        "email_configured": data.get("email_configured"),
        "smtp_status": data.get("smtp_status"),
        "permalink": data.get("permalink"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "expires_at": data.get("expires_at"),
        "sections": data.get("sections"),
        "checks": checks[:MAX_CHECKS],
    }
    payload = _payload(
        api_source="scan.mx email authentication and deliverability API",
        api_documentation=SCAN_MX_DOCS,
        endpoint=endpoint,
        invocation=SCAN_MX_INVOCATION,
        query=domain,
        records=[record],
        total=1,
        extra={"check_count": len(checks)},
    )
    return SourceResult("scan-mx", data=payload, http_status=status)


# -- checkdmarc ----------------------------------------------------------------


def _import_checkdmarc() -> Any:
    """Import checkdmarc lazily so --health works without the package."""
    import checkdmarc

    return checkdmarc


def query_checkdmarc(value: str) -> SourceResult:
    domain = _domain(value)
    if not domain:
        return _skip(
            "checkdmarc",
            "checkdmarc documents domain names, and the supplied value is not a fully qualified domain "
            "name, so it is not passed to checkdmarc.check_domains.",
        )
    try:
        checkdmarc = _import_checkdmarc()
    except Exception as exc:
        return _skip(
            "checkdmarc",
            "The checkdmarc module is not importable in this image ("
            + type(exc).__name__
            + ": "
            + str(exc)
            + "). The image installs the pinned checkdmarc package ("
            + CHECKDMARC_VERSION
            + ") and the runner imports it lazily, so the sub-source is reported as a documented skip "
            "instead of failing the run.",
        )
    try:
        result = checkdmarc.check_domains([domain])
    except Exception as exc:
        return SourceResult(
            "checkdmarc",
            error="checkdmarc.check_domains raised " + type(exc).__name__ + ": " + str(exc),
        )

    if isinstance(result, list):
        result = result[0] if result else {}
    if not isinstance(result, dict):
        try:
            result = dict(result)
        except Exception:
            return SourceResult(
                "checkdmarc",
                error="Unexpected result type from checkdmarc.check_domains: " + type(result).__name__,
            )

    mx = result.get("mx") if isinstance(result.get("mx"), dict) else {}
    spf = result.get("spf") if isinstance(result.get("spf"), dict) else {}
    dmarc = result.get("dmarc") if isinstance(result.get("dmarc"), dict) else {}
    mx_hosts = mx.get("hosts") if isinstance(mx.get("hosts"), list) else []
    spf_record = _clean(spf.get("record"))
    dmarc_record = _clean(dmarc.get("record"))
    record = {
        "record_id": domain,
        "detail": (
            "checkdmarc email-authentication result for "
            + domain
            + ": "
            + str(len(mx_hosts))
            + " MX host(s); SPF "
            + (spf_record or "not found")
            + "; DMARC "
            + (dmarc_record or "not found")
        ),
        "domain": result.get("domain") or domain,
        "base_domain": result.get("base_domain"),
        "dnssec": result.get("dnssec"),
        "mx": result.get("mx"),
        "spf": result.get("spf"),
        "dmarc": result.get("dmarc"),
    }
    payload = _payload(
        api_source="checkdmarc (Python library, DNS records checked directly)",
        api_documentation=CHECKDMARC_DOCS,
        module=CHECKDMARC_MODULE,
        invocation=CHECKDMARC_INVOCATION,
        query=domain,
        records=[record],
        total=1,
        extra={
            "entry_point": CHECKDMARC_ENTRY_POINT,
            "package_version": CHECKDMARC_VERSION,
            "package_url": CHECKDMARC_PYPI,
        },
    )
    return SourceResult("checkdmarc", data=payload)


# -- health --------------------------------------------------------------------


def _checkdmarc_available() -> bool:
    """Report importability without importing the module."""
    try:
        return importlib.util.find_spec(CHECKDMARC_MODULE) is not None
    except Exception:
        return False


def _health_inventory() -> dict[str, Any]:
    """Describe sub-source availability without any network call."""
    entries: list[dict[str, Any]] = [
        {
            "source": "scan-mx",
            "kind": "http_api",
            "usable": True,
            "endpoint": SCAN_MX_CHECK_URL,
            "module": None,
            "credential_env": None,
            "credential_configured": None,
            "detail": "keyless, no signup; reachability is not tested by --health; no network request is made",
        },
        {
            "source": "checkdmarc",
            "kind": "library",
            "usable": _checkdmarc_available(),
            "endpoint": None,
            "module": CHECKDMARC_MODULE,
            "entry_point": CHECKDMARC_ENTRY_POINT,
            "package_version": CHECKDMARC_VERSION,
            "credential_env": None,
            "credential_configured": None,
            "detail": "imported lazily inside query_checkdmarc; --health only checks importability and imports nothing",
        },
    ]
    for name in sorted(UNSUPPORTED_SUB_SOURCES):
        entries.append(
            {
                "source": name,
                "kind": "dropped",
                "usable": False,
                "endpoint": None,
                "module": None,
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
        print("input_type: domain", file=sys.stderr)
        return 2

    input_type = sys.argv[1]
    value = sys.argv[2]

    valid_types = {"domain"}
    if input_type not in valid_types:
        print(
            "Invalid input_type: " + input_type + ". Must be one of: " + str(sorted(valid_types)),
            file=sys.stderr,
        )
        return 2

    # Every implemented sub-source is reported once per run. Any dropped
    # candidate is reported as a documented skip and is never queried.
    results = [
        query_scan_mx(value),
        query_checkdmarc(value),
    ]
    for name in sorted(UNSUPPORTED_SUB_SOURCES):
        results.append(_skip(name, UNSUPPORTED_SUB_SOURCES[name]))

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
