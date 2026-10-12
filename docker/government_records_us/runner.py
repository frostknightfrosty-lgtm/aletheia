from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30, method: str = "GET", data: bytes | None = None) -> tuple[dict | list | None, int, str | None]:
    """Fetch JSON from URL. Returns (payload, http_status, error_message)."""
    req_headers = {"Accept": "application/json", "User-Agent": "Aletheia/0.7.0 (gov-records-us)"}
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


def query_finra(query: str) -> SourceResult:
    url = "https://api.finra.org/data/group/registration/name/compositeindividual"
    params = {
        "query": query,
        "limit": 50,
        "fields": "crd,firstName,middleName,lastName,nameSuffix,otherNames,bcScope,iaScope,hasBcDisclosure,hasIaDisclosure,isPermanentlyBarred,approvedFinraRegistrationCount,employmentCount,industryDays,industryEntryAt,currentEmployments"
    }
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("finra-brokercheck", http_status=status, error=err)
    return SourceResult("finra-brokercheck", data=payload, http_status=status)


def query_fdic(query: str) -> SourceResult:
    key = os.environ.get("FDIC_API_KEY")
    url = "https://api.fdic.gov/banks/v1/institutions"
    params = {"filters": f"NAME:{query.upper()}", "limit": 50}
    if key:
        params["api_key"] = key
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("fdic-bankfind", http_status=status, error=err)
    return SourceResult("fdic-bankfind", data=payload, http_status=status)


def query_fed_enforcement(query: str) -> SourceResult:
    # Static JSON feeds - query the recent feed
    url = "https://www.federalreserve.gov/supervisionreg/ea-cms-recent.json"
    payload, status, err = _fetch_json(url)
    if err:
        return SourceResult("fed-enforcement", http_status=status, error=err)
    if isinstance(payload, list):
        # Filter by name if provided
        if query:
            filtered = [item for item in payload if query.lower() in json.dumps(item).lower()]
            payload = {"filtered": True, "query": query, "results": filtered}
    return SourceResult("fed-enforcement", data=payload, http_status=status)


def query_occ_enforcement(query: str) -> SourceResult:
    key = os.environ.get("OCC_API_KEY")
    if not key:
        return SourceResult("occ-enforcement", skipped=True, skip_reason="OCC_API_KEY not set")
    url = f"https://api.occ.gov/EnforcementActions/list/{urllib.parse.quote(query)}"
    params = {"api_key": key}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("occ-enforcement", http_status=status, error=err)
    return SourceResult("occ-enforcement", data=payload, http_status=status)


def query_usaspending(query: str) -> SourceResult:
    # Search recipients by name
    url = "https://api.usaspending.gov/api/v2/recipient/list/"
    payload = {
        "keyword": query,
        "limit": 50,
        "page": 1
    }
    data_bytes = json.dumps(payload).encode()
    req_headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data_bytes, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(5_000_001)
            if len(body) > 5_000_000:
                return SourceResult("usaspending", http_status=response.status, error="Response exceeded 5 MB")
            result = json.loads(body.decode("utf-8"))
            return SourceResult("usaspending", data=result, http_status=response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return SourceResult("usaspending", http_status=exc.code, error=f"HTTP {exc.code}: {body[:500]}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return SourceResult("usaspending", http_status=0, error=f"{type(exc).__name__}: {exc}")


def query_sam_gov(query: str) -> SourceResult:
    key = os.environ.get("SAM_API_KEY")
    if not key:
        return SourceResult("sam-gov", skipped=True, skip_reason="SAM_API_KEY not set")
    url = "https://api.sam.gov/entity-information/v4/entities"
    params = {"api_key": key, "qterm": query, "limit": 50}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("sam-gov", http_status=status, error=err)
    return SourceResult("sam-gov", data=payload, http_status=status)


def query_lda(query: str) -> SourceResult:
    key = os.environ.get("LDA_API_KEY")
    url = "https://lda.senate.gov/api/v1/filings/"
    params = {"client": query, "limit": 50}
    if key:
        params["api_key"] = key
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("lda", http_status=status, error=err)
    return SourceResult("lda", data=payload, http_status=status)


def query_foia_gov(query: str) -> SourceResult:
    key = os.environ.get("FOIA_API_KEY")
    if not key:
        return SourceResult("foia-gov", skipped=True, skip_reason="FOIA_API_KEY not set")
    url = "https://api.foia.gov/api/agency_components"
    params = {"name": query}
    headers = {"X-API-Key": key}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url, headers=headers)
    if err:
        return SourceResult("foia-gov", http_status=status, error=err)
    return SourceResult("foia-gov", data=payload, http_status=status)


def query_nhtsa(vin: str) -> SourceResult:
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{urllib.parse.quote(vin)}"
    params = {"format": "json"}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("nhtsa-vpic", http_status=status, error=err)
    return SourceResult("nhtsa-vpic", data=payload, http_status=status)


def query_bop_inmate(query: str) -> SourceResult:
    # Parse name into first/last
    parts = query.strip().split()
    if len(parts) < 2:
        return SourceResult("bop-inmate-locator", http_status=400, error="Need first and last name")
    first, last = parts[0], parts[-1]
    url = "https://www.bop.gov/PublicInfo/execute/inmateloc"
    params = {"todo": "query", "output": "json", "nameLast": last, "nameFirst": first}
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("bop-inmate-locator", http_status=status, error=err)
    return SourceResult("bop-inmate-locator", data=payload, http_status=status)


def query_nyc_open_data(query: str) -> SourceResult:
    # Search 311 service requests by complaint type or agency
    # Using a common dataset: 311 Service Requests
    url = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
    params = {"$where": f"complaint_type LIKE '%{query}%' OR agency LIKE '%{query}%'", "$limit": 50}
    key = os.environ.get("NYC_OPEN_DATA_TOKEN")
    if key:
        params["$$app_token"] = key
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    payload, status, err = _fetch_json(full_url)
    if err:
        return SourceResult("nyc-open-data", http_status=status, error=err)
    return SourceResult("nyc-open-data", data=payload, http_status=status)


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        print("ok")
        return 0

    if len(sys.argv) < 3:
        print("usage: runner.py <input_type> <value>", file=sys.stderr)
        print("input_type: name, company_name, bank_name, vin, person_name, lobbyist_name", file=sys.stderr)
        return 2

    input_type = sys.argv[1]
    value = sys.argv[2]

    # Validate input type
    valid_types = {"name", "company_name", "bank_name", "vin", "person_name", "lobbyist_name"}
    if input_type not in valid_types:
        print(f"Invalid input_type: {input_type}. Must be one of: {valid_types}", file=sys.stderr)
        return 2

    results = []

    # Dispatch based on input type
    if input_type == "vin":
        results.append(query_nhtsa(value))
    elif input_type == "person_name":
        results.append(query_finra(value))
        results.append(query_bop_inmate(value))
        results.append(query_occ_enforcement(value))
        results.append(query_fed_enforcement(value))
    elif input_type in {"name", "company_name"}:
        results.append(query_finra(value))
        results.append(query_fdic(value))
        results.append(query_usaspending(value))
        results.append(query_sam_gov(value))
        results.append(query_foia_gov(value))
        results.append(query_nyc_open_data(value))
    elif input_type == "bank_name":
        results.append(query_finra(value))
        results.append(query_fdic(value))
        results.append(query_occ_enforcement(value))
        results.append(query_fed_enforcement(value))
    elif input_type == "lobbyist_name":
        results.append(query_lda(value))
        results.append(query_foia_gov(value))

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