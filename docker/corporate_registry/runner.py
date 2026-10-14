from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

# Exact documented reasons for sub-sources that publish no free public search
# API. No URL is constructed for these; they are reported as skipped so the
# limitation stays visible and auditable in every run.
INPI_RNE_SKIP_REASON = "INPI RNE exposes no documented free search API (bulk SFTP and dataset APIs only)"
ASIC_SKIP_REASON = "ASIC publishes no public JSON search API; ASIC Connect is web-only and DSP applications are closed until 2027"
CIPC_SKIP_REASON = "CIPC provides no public API; enterprise search is web-only"

# KVK Zoeken is a paid subscription that excludes private use. It stays off
# unless the operator explicitly supplies KVK_API_KEY.
KVK_ZOEKEN_SKIP_REASON = "KVK_API_KEY not set; the KVK Zoeken API is a paid subscription that excludes private use"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30, method: str = "GET", data: bytes | None = None) -> tuple[dict | list | None, int, str | None]:
    """Fetch JSON from URL. Returns (payload, http_status, error_message)."""
    req_headers = {"Accept": "application/json", "User-Agent": "Aletheia/0.7.0 (corp-registry)"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(5_000_001)
            if len(body) > 5_000_000:
                return None, response.status, "Response exceeded 5 MB safety limit"
            try:
                return json.loads(body.decode("utf-8")), response.status, None
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None, response.status, "Response was not valid JSON"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, f"HTTP {exc.code}: {body[:500]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"


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


def query_companies_house(query: str) -> SourceResult:
    key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    if not key:
        return SourceResult("companies-house", skipped=True, skip_reason="COMPANIES_HOUSE_API_KEY not set")
    url = "https://api.company-information.service.gov.uk/search/companies"
    params = {"q": query}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    # HTTP Basic auth: API key as username, empty password. The token is built
    # locally and only ever placed in the Authorization header; the key is never
    # printed or returned in output.
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    headers = {"Authorization": f"Basic {token}"}
    payload, status, err = _fetch_json(full_url, headers=headers)
    if err:
        return SourceResult("companies-house", http_status=status, error=err)
    return SourceResult("companies-house", data=payload, http_status=status)


def query_nzbn(query: str) -> SourceResult:
    key = os.environ.get("NZBN_API_SUBSCRIPTION_KEY")
    if not key:
        return SourceResult("nzbn", skipped=True, skip_reason="NZBN_API_SUBSCRIPTION_KEY not set")
    url = "https://api.business.govt.nz/gateway/nzbn/v5/entities"
    params = {"search-term": query}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {"Ocp-Apim-Subscription-Key": key}
    payload, status, err = _fetch_json(full_url, headers=headers)
    if err:
        return SourceResult("nzbn", http_status=status, error=err)
    return SourceResult("nzbn", data=payload, http_status=status)


def query_kvk_opendata(query: str) -> SourceResult:
    # Free Open Dataset. Number-keyed lookup only: the input value is used as
    # the kvknummer path segment, so a name input is answered by the provider
    # (typically a 404) rather than being turned into fabricated records.
    url = "https://opendata.kvk.nl/api/v1/hvds/basisbedrijfsgegevens/kvknummer/" + urllib.parse.quote(query, safe="")
    payload, status, err = _fetch_json(url)
    if err:
        return SourceResult("kvk-opendata", http_status=status, error=err)
    return SourceResult("kvk-opendata", data=payload, http_status=status)


def query_kvk_zoeken(query: str) -> SourceResult:
    key = os.environ.get("KVK_API_KEY")
    if not key:
        return SourceResult("kvk-zoeken", skipped=True, skip_reason=KVK_ZOEKEN_SKIP_REASON)
    url = "https://api.kvk.nl/api/v2/zoeken"
    params = {"naam": query}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {"apikey": key}
    payload, status, err = _fetch_json(full_url, headers=headers)
    if err:
        return SourceResult("kvk-zoeken", http_status=status, error=err)
    return SourceResult("kvk-zoeken", data=payload, http_status=status)


def query_recherche_entreprises(query: str) -> SourceResult:
    url = "https://recherche-entreprises.api.gouv.fr/search"
    params = {"q": query}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("recherche-entreprises", http_status=status, error=err)
    return SourceResult("recherche-entreprises", data=payload, http_status=status)


def query_inpi_rne(query: str) -> SourceResult:
    # Unsupported: INPI publishes no free query-parameter search API.
    return SourceResult("inpi-rne", skipped=True, skip_reason=INPI_RNE_SKIP_REASON)


def query_asic(query: str) -> SourceResult:
    # Unsupported: ASIC publishes no public JSON search API.
    return SourceResult("asic", skipped=True, skip_reason=ASIC_SKIP_REASON)


def query_cipc(query: str) -> SourceResult:
    # Unsupported: CIPC provides no public API.
    return SourceResult("cipc", skipped=True, skip_reason=CIPC_SKIP_REASON)


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        print("ok")
        return 0

    if len(sys.argv) < 3:
        print("usage: runner.py <input_type> <value>", file=sys.stderr)
        print("input_type: name, company_name", file=sys.stderr)
        return 2

    input_type = sys.argv[1]
    value = sys.argv[2]

    # Validate input type
    valid_types = {"name", "company_name"}
    if input_type not in valid_types:
        print(f"Invalid input_type: {input_type}. Must be one of: {valid_types}", file=sys.stderr)
        return 2

    # Every sub-source is reported once per run. Unsupported sub-sources return
    # a documented skip so the gap is visible in the run output.
    results = [
        query_companies_house(value),
        query_nzbn(value),
        query_kvk_opendata(value),
        query_kvk_zoeken(value),
        query_recherche_entreprises(value),
        query_inpi_rne(value),
        query_asic(value),
        query_cipc(value),
    ]

    output = {
        "input_type": input_type,
        "input_value": value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [r.to_dict() for r in results],
    }

    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
