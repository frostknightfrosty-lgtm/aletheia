"""Bounded, keyless aircraft-registry and railway-facility lookups.

The source endpoints, request limits, and drops are recorded in RATE_LIMITS.md.
`--health` performs no network request and prints exactly `ok` on stdout.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

FAA_DOCS = "https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download/index.cfm"
FAA_FIELDS_DOCS = "https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/media/ardata.pdf"
FAA_ARCHIVE_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
OPENRAILWAYMAP_DOCS = "https://github.com/OpenRailwayMap/OpenRailwayMap-api/blob/master/README.md"
OPENRAILWAYMAP_URL = "https://api.openrailwaymap.org/v2/facility"
PLANESPOTTERS_DOCS = "https://www.planespotters.net/legal/termsofuse?desktop=true"
PLANESPOTTERS_BASE = "https://api.planespotters.net/pub/photos"
USER_AGENT = "Aletheia/1.0 (+https://github.com/frostknightfrosty-lgtm/aletheia)"

SUPPORTED_SUB_SOURCES = (
    "faa-aircraft-registration",
    "openrailwaymap",
    "planespotters",
)

UNSUPPORTED_SUB_SOURCES = {
    "imo-gisis": (
        "IMO documents the Ship and Company Particulars module as a public browser search, but no "
        "public machine-readable request contract or API was found in the official GISIS material. "
        "The adapter does not automate the browser portal or invent a hidden endpoint. See "
        "https://www.imo.org/en/mediacentre/pages/whatsnew-1704.aspx and "
        "https://gisis.imo.org/Public/Default.aspx."
    ),
    "eratv": (
        "ERA's official Knowledge Graph coverage page marks ERATV migration as ongoing, so the public "
        "SPARQL service is not a verified ERATV data endpoint yet. The ERATV browser interface also "
        "uses CAPTCHA after repeated public view/export attempts; the adapter does not automate or "
        "bypass that challenge. See https://www.era.europa.eu/cs/node/1665 and "
        "https://www.era.europa.eu/system/files/2022-11/eratv_usm_deployment_end-user_support_material_user_manual_nas_en.pdf."
    ),
    "eris": (
        "No official railway asset registry or public endpoint corresponding to the name ERIS was "
        "identified in the reviewed ERA sources. The batching plan names ERATV, not ERIS; no endpoint "
        "is inferred from the ambiguous acronym. See https://www.era.europa.eu/cs/node/1665."
    ),
}

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_FAA_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_FAA_MASTER_BYTES = 512 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 15
OPENRAILWAYMAP_TIMEOUT_SECONDS = 5


class SourceResult:
    def __init__(
        self,
        name: str,
        *,
        data: dict[str, Any] | None = None,
        http_status: int = 0,
        error: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
    ) -> None:
        self.name = name
        self.data = data
        self.http_status = http_status
        self.error = error
        self.skipped = skipped
        self.skip_reason = skip_reason
        self.timestamp = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(data, sort_keys=True).encode() if data is not None else b""
        self.raw_hash = hashlib.sha256(encoded).hexdigest() if data is not None else None

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
    return SourceResult(name, skipped=True, skip_reason=reason)


def _request_bytes(
    url: str,
    *,
    timeout: int,
    max_bytes: int,
    accept: str,
) -> tuple[bytes | None, int, str | None]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                return None, response.status, f"Response exceeded {max_bytes} bytes"
            return body, response.status, None
    except urllib.error.HTTPError as exc:
        # Do not retry; specifically, OpenRailwayMap requires callers to stop on 429.
        return None, exc.code, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, type(exc).__name__ + ": " + str(exc)


def _request_json(
    url: str,
    *,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> tuple[Any, int, str | None]:
    body, status, error = _request_bytes(
        url,
        timeout=timeout,
        max_bytes=MAX_JSON_BYTES,
        accept="application/json",
    )
    if error:
        return None, status, error
    try:
        return json.loads((body or b"").decode("utf-8-sig")), status, None
    except json.JSONDecodeError as exc:
        return None, status, "JSON decode error: " + str(exc)


def _is_n_number(value: str) -> bool:
    normalized = value.strip().upper()
    return bool(re.fullmatch(r"N[1-9][0-9]{0,4}[A-Z]{0,2}", normalized))


def _is_hex_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9A-Fa-f]{6}", value.strip()))


def _is_aircraft_registration(value: str) -> bool:
    normalized = value.strip().upper()
    return _is_n_number(normalized) or bool(
        re.fullmatch(r"[A-Z0-9]{1,3}-[A-Z0-9]{2,5}", normalized)
    )


def _faa_record_from_archive(archive_bytes: bytes, registration: str) -> dict[str, Any] | None:
    target = registration.strip().upper()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        master = next(
            (
                member
                for member in archive.infolist()
                if PurePosixPath(member.filename).name.upper() in {"MASTER", "MASTER.TXT", "MASTER.CSV"}
            ),
            None,
        )
        if master is None:
            raise ValueError("FAA archive did not contain the documented master file")
        if master.file_size > MAX_FAA_MASTER_BYTES:
            raise ValueError("FAA master file exceeded the decompressed-size safety limit")
        with archive.open(master, "r") as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            for row in csv.reader(text):
                if len(row) < 5 or row[0].strip().upper() != target:
                    continue
                # The FAA field guide describes a comma-delimited 612-character
                # master record. These indices correspond to the documented field
                # positions; registrant identity/address fields are intentionally
                # never copied into the result.
                def field(index: int) -> str | None:
                    value = row[index].strip() if len(row) > index else ""
                    return value or None

                return {
                    "record_type": "faa_aircraft_registration",
                    "registration": field(0),
                    "serial_number": field(1),
                    "manufacturer_model_code": field(2),
                    "year_manufactured": field(4),
                    "aircraft_type_code": field(19),
                    "engine_type_code": field(20),
                    "status_code": field(21),
                    "mode_s_code": field(22),
                    "mode_s_code_hex": field(34),
                    "endpoint": FAA_ARCHIVE_URL,
                    "documentation": FAA_FIELDS_DOCS,
                }
    return None


def query_faa(value: str) -> SourceResult:
    if not _is_n_number(value):
        return _skip(
            "faa-aircraft-registration",
            "FAA aircraft registry lookup accepts an exact U.S. N-number only; this seed is not an N-number.",
        )
    body, status, error = _request_bytes(
        FAA_ARCHIVE_URL,
        timeout=120,
        max_bytes=MAX_FAA_ARCHIVE_BYTES,
        accept="application/zip,application/octet-stream",
    )
    if error:
        return SourceResult("faa-aircraft-registration", http_status=status, error=error)
    try:
        record = _faa_record_from_archive(body or b"", value)
    except (OSError, ValueError, zipfile.BadZipFile, csv.Error) as exc:
        return SourceResult("faa-aircraft-registration", http_status=status, error="FAA archive parse error: " + str(exc))
    if record is None:
        return SourceResult("faa-aircraft-registration", http_status=status)
    record["record_id"] = record.get("registration")
    record["detail"] = "FAA public aircraft registration master record"
    return SourceResult(
        "faa-aircraft-registration",
        http_status=status,
        data={
            "api_source": "FAA Releasable Aircraft Database",
            "api_documentation": FAA_DOCS,
            "endpoint": FAA_ARCHIVE_URL,
            "query": value.strip().upper(),
            "record_count": 1,
            "records": [record],
        },
    )


def query_planespotters(value: str) -> SourceResult:
    normalized = value.strip().upper()
    if _is_hex_identifier(normalized):
        endpoint = PLANESPOTTERS_BASE + "/hex/" + urllib.parse.quote(normalized, safe="")
        invocation = "GET https://api.planespotters.net/pub/photos/hex/<hex>"
    elif _is_aircraft_registration(normalized):
        endpoint = PLANESPOTTERS_BASE + "/reg/" + urllib.parse.quote(normalized, safe="")
        invocation = "GET https://api.planespotters.net/pub/photos/reg/<registration>"
    else:
        return _skip(
            "planespotters",
            "Planespotters accepts an exact aircraft registration or six-character ICAO hex identifier; this seed is neither.",
        )
    response, status, error = _request_json(endpoint)
    if error:
        return SourceResult("planespotters", http_status=status, error=error)
    if not isinstance(response, dict) or not isinstance(response.get("photos"), list):
        return SourceResult("planespotters", http_status=status, error="Unexpected Planespotters response shape")
    records = []
    for photo in response["photos"][:5]:
        if not isinstance(photo, dict):
            continue
        # Never include image or thumbnail URLs; keep the reference/attribution metadata only.
        records.append(
            {
                "record_id": str(photo.get("id") or normalized),
                "registration": normalized if not _is_hex_identifier(normalized) else None,
                "hex_identifier": normalized if _is_hex_identifier(normalized) else None,
                "record_type": "aircraft_photo_reference",
                "photographer": photo.get("photographer"),
                "source_page": photo.get("link"),
                "detail": "Planespotters public aircraft-photo reference; image bytes not downloaded",
            }
        )
    return SourceResult(
        "planespotters",
        http_status=status,
        data={
            "api_source": "Planespotters public photo metadata endpoint",
            "api_documentation": PLANESPOTTERS_DOCS,
            "endpoint": endpoint,
            "invocation": invocation,
            "query": normalized,
            "record_count": len(records),
            "records": records,
        } if records else None,
    )


def query_openrailwaymap(value: str) -> SourceResult:
    normalized = value.strip()
    if _is_aircraft_registration(normalized) or _is_hex_identifier(normalized):
        return _skip(
            "openrailwaymap",
            "OpenRailwayMap facility search is only used for a railway facility name or uic:<reference> seed.",
        )
    if normalized.lower().startswith("uic:"):
        query_value = normalized[4:].strip()
        if not query_value:
            return SourceResult("openrailwaymap", error="uic: seed requires a non-empty UIC reference")
        query_key = "uic_ref"
    else:
        query_value = normalized
        query_key = "name"
    endpoint = OPENRAILWAYMAP_URL + "?" + urllib.parse.urlencode({query_key: query_value, "limit": "5"})
    response, status, error = _request_json(endpoint, timeout=OPENRAILWAYMAP_TIMEOUT_SECONDS)
    if error:
        return SourceResult("openrailwaymap", http_status=status, error=error)
    if not isinstance(response, list):
        return SourceResult("openrailwaymap", http_status=status, error="Unexpected OpenRailwayMap response shape")
    records = []
    for facility in response[:5]:
        if not isinstance(facility, dict):
            continue
        fields = {
            key: facility[key]
            for key in (
                "osm_id", "name", "railway", "ref", "uic_ref", "operator",
                "latitude", "longitude", "website", "public_transport",
            )
            if facility.get(key) is not None
        }
        records.append(
            {
                "record_id": str(facility.get("osm_id") or facility.get("uic_ref") or facility.get("name") or query_value),
                "record_type": "railway_facility",
                "name": facility.get("name"),
                "source_fields": fields,
                "detail": "OpenRailwayMap / OpenStreetMap facility metadata",
            }
        )
    return SourceResult(
        "openrailwaymap",
        http_status=status,
        data={
            "api_source": "OpenRailwayMap facility API",
            "api_documentation": OPENRAILWAYMAP_DOCS,
            "endpoint": endpoint,
            "query": query_value,
            "record_count": len(records),
            "records": records,
        } if records else None,
    )


def _health_inventory() -> dict[str, Any]:
    entries = [
        {
            "source": "faa-aircraft-registration",
            "kind": "public_csv_archive",
            "usable": True,
            "endpoint": FAA_ARCHIVE_URL,
            "key_configured": False,
        },
        {
            "source": "openrailwaymap",
            "kind": "public_json_api",
            "usable": True,
            "endpoint": OPENRAILWAYMAP_URL,
            "key_configured": False,
        },
        {
            "source": "planespotters",
            "kind": "keyless_json_endpoint",
            "usable": True,
            "endpoint": PLANESPOTTERS_BASE,
            "key_configured": False,
        },
    ]
    for name, reason in sorted(UNSUPPORTED_SUB_SOURCES.items()):
        entries.append({
            "source": name,
            "kind": "dropped",
            "usable": False,
            "endpoint": None,
            "key_configured": False,
            "detail": reason,
        })
    return {"health": "ok", "network_used": False, "sub_sources": entries}


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        print(json.dumps(_health_inventory(), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        print("ok")
        return 0
    if len(sys.argv) != 3 or sys.argv[1] != "name":
        print("usage: runner.py name <registration|icao-hex|railway-facility-name|uic:reference>", file=sys.stderr)
        return 2
    value = sys.argv[2].strip()
    if not value:
        print("seed must not be empty", file=sys.stderr)
        return 2
    results = [
        query_faa(value),
        query_openrailwaymap(value),
        query_planespotters(value),
        *(_skip(name, reason) for name, reason in sorted(UNSUPPORTED_SUB_SOURCES.items())),
    ]
    output = {
        "input_type": "name",
        "input_value": value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [result.to_dict() for result in results],
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
