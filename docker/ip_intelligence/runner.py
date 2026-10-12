from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except (ValueError, TypeError):
        return None


def _normalize_cidr(value: str) -> str | None:
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except (ValueError, TypeError):
        return None


def _fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[dict | list | None, int, str | None]:
    """Fetch JSON from URL. Returns (payload, http_status, error_message)."""
    req_headers = {"Accept": "application/json", "User-Agent": "Aletheia/0.7.0 (ip-intelligence)"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                return None, response.status, "Response exceeded 2 MB safety limit"
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


def query_ipinfo(ip: str) -> SourceResult:
    token = os.environ.get("IPINFO_TOKEN")
    if not token:
        return SourceResult("ipinfo", skipped=True, skip_reason="IPINFO_TOKEN not set")
    url = f"https://ipinfo.io/{ip}/json?token={token}"
    payload, status, err = _fetch_json(url)
    if err:
        return SourceResult("ipinfo", http_status=status, error=err)
    return SourceResult("ipinfo", data=payload, http_status=status)


def query_ipapi(ip: str) -> SourceResult:
    url = f"http://ip-api.com/json/{ip}?fields=status,message,continent,continentCode,country,countryCode,region,regionName,city,district,zip,lat,lon,timezone,offset,currency,isp,org,as,asname,reverse,mobile,proxy,hosting,query"
    payload, status, err = _fetch_json(url)
    if err:
        return SourceResult("ip-api", http_status=status, error=err)
    if isinstance(payload, dict) and payload.get("status") == "fail":
        return SourceResult("ip-api", data=payload, http_status=status, error=payload.get("message"))
    return SourceResult("ip-api", data=payload, http_status=status)


def query_ipapi_co(ip: str) -> SourceResult:
    key = os.environ.get("IPAPI_CO_KEY")
    url = f"https://ipapi.co/{ip}/json/"
    if key:
        url += f"?key={key}"
    payload, status, err = _fetch_json(url)
    if err:
        return SourceResult("ipapi-co", http_status=status, error=err)
    if isinstance(payload, dict) and payload.get("error"):
        return SourceResult("ipapi-co", data=payload, http_status=status, error=payload.get("reason"))
    return SourceResult("ipapi-co", data=payload, http_status=status)


def query_ipgeolocation(ip: str) -> SourceResult:
    key = os.environ.get("IPGEOLOCATION_KEY")
    if not key:
        return SourceResult("ipgeolocation", skipped=True, skip_reason="IPGEOLOCATION_KEY not set")
    url = f"https://api.ipgeolocation.io/ipgeo?apiKey={key}&ip={ip}"
    payload, status, err = _fetch_json(url)
    if err:
        return SourceResult("ipgeolocation", http_status=status, error=err)
    return SourceResult("ipgeolocation", data=payload, http_status=status)


def query_abuseipdb(ip: str) -> SourceResult:
    key = os.environ.get("ABUSEIPDB_KEY")
    if not key:
        return SourceResult("abuseipdb", skipped=True, skip_reason="ABUSEIPDB_KEY not set")
    url = f"https://api.abuseipdb.com/api/v2/check?ipAddress={ip}&maxAgeInDays=90&verbose=true"
    payload, status, err = _fetch_json(url, headers={"Key": key, "Accept": "application/json"})
    if err:
        return SourceResult("abuseipdb", http_status=status, error=err)
    return SourceResult("abuseipdb", data=payload, http_status=status)


def query_greynoise(ip: str) -> SourceResult:
    key = os.environ.get("GREYNOISE_KEY")
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    url = f"https://api.greynoise.io/v3/community/{ip}"
    payload, status, err = _fetch_json(url, headers=headers)
    if err:
        return SourceResult("greynoise", http_status=status, error=err)
    return SourceResult("greynoise", data=payload, http_status=status)


def query_virustotal(ip: str) -> SourceResult:
    key = os.environ.get("VIRUSTOTAL_KEY")
    if not key:
        return SourceResult("virustotal", skipped=True, skip_reason="VIRUSTOTAL_KEY not set")
    url = f"https://www.virustotal.com/api/v3/ip_addresses/{ip}"
    payload, status, err = _fetch_json(url, headers={"x-apikey": key})
    if err:
        return SourceResult("virustotal", http_status=status, error=err)
    return SourceResult("virustotal", data=payload, http_status=status)


def query_urlhaus(ip: str) -> SourceResult:
    key = os.environ.get("URLHAUS_AUTH_KEY")
    if not key:
        return SourceResult("urlhaus", skipped=True, skip_reason="URLHAUS_AUTH_KEY not set")
    url = "https://urlhaus-api.abuse.ch/v1/host/"
    payload = {"host": ip}
    req_headers = {"Auth-Key": key, "Content-Type": "application/json"}
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                return SourceResult("urlhaus", http_status=response.status, error="Response exceeded 2 MB")
            data = json.loads(body.decode("utf-8"))
            return SourceResult("urlhaus", data=data, http_status=response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return SourceResult("urlhaus", http_status=exc.code, error=f"HTTP {exc.code}: {body[:500]}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return SourceResult("urlhaus", http_status=0, error=f"{type(exc).__name__}: {exc}")


def query_threatfox(ip: str) -> SourceResult:
    key = os.environ.get("THREATFOX_AUTH_KEY")
    if not key:
        return SourceResult("threatfox", skipped=True, skip_reason="THREATFOX_AUTH_KEY not set")
    url = "https://threatfox-api.abuse.ch/api/v1/"
    payload = {"query": "search_ioc", "search_term": ip}
    req_headers = {"Auth-Key": key, "Content-Type": "application/json"}
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                return SourceResult("threatfox", http_status=response.status, error="Response exceeded 2 MB")
            data = json.loads(body.decode("utf-8"))
            return SourceResult("threatfox", data=data, http_status=response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return SourceResult("threatfox", http_status=exc.code, error=f"HTTP {exc.code}: {body[:500]}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return SourceResult("threatfox", http_status=0, error=f"{type(exc).__name__}: {exc}")


def query_malwarebazaar(ip: str) -> SourceResult:
    key = os.environ.get("MALWAREBAZAAR_AUTH_KEY")
    if not key:
        return SourceResult("malwarebazaar", skipped=True, skip_reason="MALWAREBAZAAR_AUTH_KEY not set")
    url = "https://mb-api.abuse.ch/api/v1/"
    payload = {"query": "get_info", "hash": ip}
    req_headers = {"Auth-Key": key, "Content-Type": "application/x-www-form-urlencoded"}
    request = urllib.request.Request(url, data=f"query=get_info&hash={ip}".encode(), headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                return SourceResult("malwarebazaar", http_status=response.status, error="Response exceeded 2 MB")
            data = json.loads(body.decode("utf-8"))
            return SourceResult("malwarebazaar", data=data, http_status=response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return SourceResult("malwarebazaar", http_status=exc.code, error=f"HTTP {exc.code}: {body[:500]}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return SourceResult("malwarebazaar", http_status=0, error=f"{type(exc).__name__}: {exc}")


def query_phishtank(ip: str) -> SourceResult:
    key = os.environ.get("PHISHTANK_APP_KEY")
    url = "https://checkurl.phishtank.com/checkurl/"
    data = {"url": ip, "format": "json"}
    if key:
        data["app_key"] = key
    req_headers = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Aletheia/0.7.0"}
    request = urllib.request.Request(url, data="&".join(f"{k}={urllib.parse.quote(v)}" for k, v in data.items()).encode(), headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                return SourceResult("phishtank", http_status=response.status, error="Response exceeded 2 MB")
            data = json.loads(body.decode("utf-8"))
            return SourceResult("phishtank", data=data, http_status=response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return SourceResult("phishtank", http_status=exc.code, error=f"HTTP {exc.code}: {body[:500]}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return SourceResult("phishtank", http_status=0, error=f"{type(exc).__name__}: {exc}")


def query_netlas(ip: str) -> SourceResult:
    key = os.environ.get("NETLAS_KEY")
    if not key:
        return SourceResult("netlas", skipped=True, skip_reason="NETLAS_KEY not set")
    url = f"https://app.netlas.io/api/domains/?q=ip:{ip}&source_type=include&fields=*"
    payload, status, err = _fetch_json(url, headers={"Authorization": f"Bearer {key}"})
    if err:
        return SourceResult("netlas", http_status=status, error=err)
    return SourceResult("netlas", data=payload, http_status=status)


def query_fullhunt(ip: str) -> SourceResult:
    key = os.environ.get("FULLHUNT_KEY")
    if not key:
        return SourceResult("fullhunt", skipped=True, skip_reason="FULLHUNT_KEY not set")
    url = f"https://fullhunt.io/api/v1/host/{ip}"
    payload, status, err = _fetch_json(url, headers={"X-API-KEY": key})
    if err:
        return SourceResult("fullhunt", http_status=status, error=err)
    return SourceResult("fullhunt", data=payload, http_status=status)


def query_hackertarget(ip: str) -> SourceResult:
    url = f"https://api.hackertarget.com/hostsearch/?q={ip}"
    payload, status, err = _fetch_json(url)
    if err:
        return SourceResult("hackertarget", http_status=status, error=err)
    return SourceResult("hackertarget", data={"hostsearch": payload}, http_status=status)


def query_ipinfo_app_asn(ip: str) -> SourceResult:
    url = f"https://ip2asn.ipinfo.app/api/v1/{ip}"
    payload, status, err = _fetch_json(url)
    if err:
        return SourceResult("ipinfo-app-asn", http_status=status, error=err)
    return SourceResult("ipinfo-app-asn", data=payload, http_status=status)


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        print("ok")
        return 0

    if len(sys.argv) < 2:
        print("usage: runner.py <ip|cidr>", file=sys.stderr)
        return 2

    target = sys.argv[1]
    is_cidr = "/" in target
    normalized_target = _normalize_cidr(target) if is_cidr else _normalize_ip(target)

    if not normalized_target:
        print(f"Invalid IP or CIDR: {target}", file=sys.stderr)
        return 2

    ip = normalized_target.split("/")[0] if is_cidr else normalized_target

    results = []

    results.append(query_ipinfo(ip))
    results.append(query_ipapi(ip))
    results.append(query_ipapi_co(ip))
    results.append(query_ipgeolocation(ip))
    results.append(query_abuseipdb(ip))
    results.append(query_greynoise(ip))
    results.append(query_virustotal(ip))
    results.append(query_urlhaus(ip))
    results.append(query_threatfox(ip))
    results.append(query_malwarebazaar(ip))
    results.append(query_phishtank(ip))
    results.append(query_netlas(ip))
    results.append(query_fullhunt(ip))
    results.append(query_hackertarget(ip))
    results.append(query_ipinfo_app_asn(ip))

    output = {
        "target": normalized_target,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [r.to_dict() for r in results],
    }

    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    import urllib.parse
    raise SystemExit(main())