"""Bounded geolocation and image-forensics composite runner.

Every endpoint, request parameter, authentication method, local command and
version pin is recorded in RATE_LIMITS.md from the relevant source's own
documentation. --health performs no network request and starts no analysis tool.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_SUB_SOURCES = (
    "mapillary",
    "nominatim",
    "copernicus-stac",
    "dfit",
    "steg-analyzer",
)

UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "pic-image-search": (
        "PicImageSearch documents a wrapper over many third-party reverse-image engines, but no "
        "single downstream engine request contract is documented by that engine for this integration. "
        "The runner therefore does not select or scrape an undocumented engine endpoint."
    ),
    "tracelines": (
        "tracelines documents deployment of its own coverage proxy and fuses Mapillary, KartaView "
        "and street-view coverage. It is not a public hosted API, and its Mapillary path would overlap "
        "the direct Mapillary source implemented here."
    ),
    "shadowfinder": (
        "ShadowFinder requires object height plus shadow length (or sun altitude) and a date/time. "
        "The current single-seed CLI provides no safe structured representation for those independent "
        "measurements, so it cannot be invoked without inventing inputs."
    ),
    "pybdshadow": (
        "pybdshadow requires building geometry and a datetime. The current single-seed CLI supplies "
        "neither a building GeoDataFrame nor a documented building-source contract, so it cannot be "
        "invoked without inventing inputs or re-querying another adapter."
    ),
    "youtube-geofind": (
        "youtube-geofind calls the YouTube Data API geospatial search. Aletheia already has the "
        "youtube-api adapter for that live vendor API, and this batch must not re-query a sub-source "
        "already live in another adapter."
    ),
    "geolocator": (
        "The reviewed GeoLocator implementations require a prebuilt panorama index and automatic model "
        "weight/index acquisition or GPU setup. No pinned, bounded single-image library contract was "
        "verified for this Docker batch."
    ),
    "betaface": (
        "Betaface documents its public betafaceapi.com service as temporarily down. The available product "
        "page does not publish a current detection request contract that this adapter can call without "
        "guessing an endpoint or credentials."
    ),
}

# Official documentation constants. The environment variable is Aletheia's
# configuration name; Mapillary documents the Authorization: OAuth <token>
# header rather than an environment variable name.
MAPILLARY_DOCS = "https://mapillary.github.io/mapillary-python-sdk/docs/mapillary.models/mapillary.models.client/"
MAPILLARY_IMAGES_URL = "https://graph.mapillary.com/images"
MAPILLARY_TOKEN_ENV = "MAPILLARY_ACCESS_TOKEN"
NOMINATIM_DOCS = "https://nominatim.org/release-docs/latest/api/Search/"
NOMINATIM_REVERSE_DOCS = "https://nominatim.org/release-docs/latest/api/Reverse/"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
COPERNICUS_DOCS = "https://documentation.dataspace.copernicus.eu/APIs/STAC.html"
COPERNICUS_STAC_ITEMS_URL = "https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-l2a/items"
DFIT_DOCS = "https://pypi.org/project/dfit-toolkit/1.0.0/"
STEG_ANALYZER_DOCS = "https://pypi.org/project/steg-analyzer/"

MAPILLARY_FIELDS = "id,captured_at,computed_geometry,compass_angle,thumb_1024_url"
MAX_RECORDS = 5
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30
TOOL_TIMEOUT_SECONDS = 120
COORDINATE_BBOX_HALF_SPAN = 0.001
USER_AGENT = "Aletheia/0.9.0 (geolocation-image)"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


class SourceResult:
    def __init__(
        self,
        name: str,
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
    return SourceResult(name, skipped=True, skip_reason=reason)


def _fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[Any, int, str | None]:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json,application/json,*/*"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return None, response.status, "Response exceeded 8 MB safety limit"
            return json.loads(body.decode("utf-8", errors="replace")), response.status, None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, f"HTTP {exc.code}: {detail[:500]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"
    except json.JSONDecodeError as exc:
        return None, 0, f"JSON decode error: {exc}"


def _parse_geolocation(value: str) -> tuple[float, float, str | None] | None:
    parts = [part.strip() for part in value.split(",", 2)]
    if len(parts) < 2:
        return None
    try:
        latitude = float(parts[0])
        longitude = float(parts[1])
    except ValueError:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude, parts[2] if len(parts) == 3 and parts[2] else None


def _bbox(latitude: float, longitude: float) -> str:
    """Make a bounded Mapillary/STAC bbox around one supplied coordinate.

    The documented services require a bbox. The half-span is an Aletheia input
    convention, not a vendor parameter name or undocumented service feature.
    """
    west = max(-180.0, longitude - COORDINATE_BBOX_HALF_SPAN)
    south = max(-90.0, latitude - COORDINATE_BBOX_HALF_SPAN)
    east = min(180.0, longitude + COORDINATE_BBOX_HALF_SPAN)
    north = min(90.0, latitude + COORDINATE_BBOX_HALF_SPAN)
    return f"{west},{south},{east},{north}"


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
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "api_source": api_source,
        "api_documentation": api_documentation,
        "query": query,
        "record_count": total,
        "truncated": total > len(records),
        "records": records,
    }
    if endpoint is not None:
        result["endpoint"] = endpoint
    if module is not None:
        result["module"] = module
    if invocation is not None:
        result["invocation"] = invocation
    return result


def query_nominatim(input_type: str, value: str) -> SourceResult:
    if input_type == "name":
        endpoint = NOMINATIM_SEARCH_URL + "?" + urllib.parse.urlencode(
            {"q": value, "format": "jsonv2", "limit": MAX_RECORDS, "addressdetails": 1}
        )
        docs = NOMINATIM_DOCS
    elif input_type == "geolocation":
        parsed = _parse_geolocation(value)
        if parsed is None:
            return _skip("nominatim", "Invalid geolocation; expected latitude,longitude[,datetime].")
        latitude, longitude, _ = parsed
        endpoint = NOMINATIM_REVERSE_URL + "?" + urllib.parse.urlencode(
            {"lat": latitude, "lon": longitude, "format": "jsonv2", "addressdetails": 1}
        )
        docs = NOMINATIM_REVERSE_DOCS
    else:
        return _skip("nominatim", "Nominatim accepts name or geolocation seeds; this run supplied an image.")
    body, status, error = _fetch_json(endpoint)
    if error:
        return SourceResult("nominatim", http_status=status, error=error)
    raw_records = body if isinstance(body, list) else [body] if isinstance(body, dict) else []
    records: list[dict[str, Any]] = []
    for item in raw_records[:MAX_RECORDS]:
        if not isinstance(item, dict):
            continue
        lat = item.get("lat")
        lon = item.get("lon")
        location = {"latitude": lat, "longitude": lon}
        records.append(
            {
                "record_id": f"{item.get('osm_type', 'place')}:{item.get('osm_id', item.get('place_id', 'unknown'))}",
                "detail": item.get("display_name"),
                "location": location,
                "source_fields": {
                    "place_id": item.get("place_id"),
                    "osm_type": item.get("osm_type"),
                    "osm_id": item.get("osm_id"),
                    "category": item.get("category", item.get("class")),
                    "type": item.get("type"),
                    "importance": item.get("importance"),
                    "boundingbox": item.get("boundingbox"),
                },
            }
        )
    if not records:
        return SourceResult("nominatim", http_status=status)
    return SourceResult(
        "nominatim",
        data=_payload(
            api_source="OpenStreetMap Nominatim",
            api_documentation=docs,
            endpoint=endpoint,
            invocation=(
                "GET https://nominatim.openstreetmap.org/search?q=<query>&format=jsonv2&limit=<limit>&addressdetails=1"
                if input_type == "name"
                else "GET https://nominatim.openstreetmap.org/reverse?lat=<lat>&lon=<lon>&format=jsonv2&addressdetails=1"
            ),
            query=value,
            records=records,
            total=len(raw_records),
        ),
        http_status=status,
    )


def query_mapillary(input_type: str, value: str) -> SourceResult:
    if input_type != "geolocation":
        return _skip("mapillary", "Mapillary requires a geolocation seed to construct its documented bbox parameter.")
    token = os.environ.get(MAPILLARY_TOKEN_ENV, "").strip()
    if not token:
        return _skip("mapillary", "MAPILLARY_ACCESS_TOKEN is required for the documented Mapillary Graph API authorization header.")
    parsed = _parse_geolocation(value)
    if parsed is None:
        return _skip("mapillary", "Invalid geolocation; expected latitude,longitude[,datetime].")
    latitude, longitude, _ = parsed
    endpoint = MAPILLARY_IMAGES_URL + "?" + urllib.parse.urlencode(
        {"fields": MAPILLARY_FIELDS, "bbox": _bbox(latitude, longitude), "limit": MAX_RECORDS}
    )
    body, status, error = _fetch_json(endpoint, headers={"Authorization": "OAuth " + token})
    if error:
        return SourceResult("mapillary", http_status=status, error=error)
    raw_records = body.get("data", []) if isinstance(body, dict) else []
    records: list[dict[str, Any]] = []
    for item in raw_records[:MAX_RECORDS]:
        if not isinstance(item, dict):
            continue
        geometry = item.get("computed_geometry")
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        location = {"longitude": coordinates[0], "latitude": coordinates[1]} if isinstance(coordinates, list) and len(coordinates) >= 2 else None
        records.append(
            {
                "record_id": item.get("id"),
                "detail": "Mapillary street-level image metadata",
                "location": location,
                "observation_time": item.get("captured_at"),
                "source_fields": {
                    "computed_geometry": geometry,
                    "compass_angle": item.get("compass_angle"),
                    "thumb_1024_url": item.get("thumb_1024_url"),
                },
            }
        )
    if not records:
        return SourceResult("mapillary", http_status=status)
    return SourceResult(
        "mapillary",
        data=_payload(
            api_source="Mapillary Graph API v4 Images",
            api_documentation=MAPILLARY_DOCS,
            endpoint=endpoint,
            invocation="GET https://graph.mapillary.com/images?fields=<fields>&bbox=<west,south,east,north>&limit=<limit>",
            query=value,
            records=records,
            total=len(raw_records),
        ),
        http_status=status,
    )


def query_copernicus_stac(input_type: str, value: str) -> SourceResult:
    if input_type != "geolocation":
        return _skip("copernicus-stac", "Copernicus STAC catalogue search requires a geolocation seed with a datetime interval.")
    parsed = _parse_geolocation(value)
    if parsed is None:
        return _skip("copernicus-stac", "Invalid geolocation; expected latitude,longitude,datetime-interval.")
    latitude, longitude, datetime_interval = parsed
    if not datetime_interval:
        return _skip("copernicus-stac", "Copernicus STAC requires a datetime interval; provide latitude,longitude,datetime-interval.")
    endpoint = COPERNICUS_STAC_ITEMS_URL + "?" + urllib.parse.urlencode(
        {"bbox": _bbox(latitude, longitude), "datetime": datetime_interval, "limit": MAX_RECORDS}
    )
    body, status, error = _fetch_json(endpoint)
    if error:
        return SourceResult("copernicus-stac", http_status=status, error=error)
    raw_records = body.get("features", []) if isinstance(body, dict) else []
    records: list[dict[str, Any]] = []
    for item in raw_records[:MAX_RECORDS]:
        if not isinstance(item, dict):
            continue
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        records.append(
            {
                "record_id": item.get("id"),
                "detail": "Copernicus Sentinel-2 L2A catalogue item",
                "location": {"bbox": item.get("bbox"), "geometry": item.get("geometry")},
                "observation_time": properties.get("datetime"),
                "source_fields": {
                    "collection": item.get("collection"),
                    "datetime": properties.get("datetime"),
                    "start_datetime": properties.get("start_datetime"),
                    "end_datetime": properties.get("end_datetime"),
                    "eo:cloud_cover": properties.get("eo:cloud_cover"),
                },
            }
        )
    if not records:
        return SourceResult("copernicus-stac", http_status=status)
    return SourceResult(
        "copernicus-stac",
        data=_payload(
            api_source="Copernicus Data Space Ecosystem STAC catalogue",
            api_documentation=COPERNICUS_DOCS,
            endpoint=endpoint,
            invocation="GET https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-l2a/items?bbox=<bbox>&datetime=<datetime>&limit=<limit>",
            query=value,
            records=records,
            total=len(raw_records),
        ),
        http_status=status,
    )


def _run_tool(argv: list[str]) -> tuple[int, str, str, str | None]:
    try:
        complete = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return 127, "", "", "binary not found: " + argv[0]
    except subprocess.TimeoutExpired:
        return 124, "", "", "timed out after " + str(TOOL_TIMEOUT_SECONDS) + " seconds"
    except OSError as exc:
        return 126, "", "", f"{type(exc).__name__}: {exc}"
    return complete.returncode, complete.stdout or "", complete.stderr or "", None


def _analysis_summary(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    keys = sorted(report) if isinstance(report, dict) else []
    # Do not propagate arbitrary text from image metadata or an analysis report.
    # This runner is intentionally an evidence summary, not a credential parser.
    return {"report_sha256": _sha256(report_path.read_bytes()), "top_level_keys": keys}


def query_dfit(input_type: str, value: str) -> SourceResult:
    if input_type != "image":
        return _skip("dfit", "DFIT requires an image or file-path seed staged inside the container.")
    with tempfile.TemporaryDirectory() as temporary:
        report_path = Path(temporary) / "dfit-metadata.json"
        command = ["dfit", "metadata", "-i", value, "-o", str(report_path)]
        code, _, stderr, failure = _run_tool(command)
        if failure:
            return SourceResult("dfit", error=failure)
        if code != 0:
            return SourceResult("dfit", error=f"dfit exited with code {code}: {stderr[-300:]}")
        if not report_path.is_file():
            return SourceResult("dfit", error="dfit completed without the documented JSON report file")
        try:
            summary = _analysis_summary(report_path)
        except (OSError, json.JSONDecodeError) as exc:
            return SourceResult("dfit", error=f"Unable to read dfit JSON report: {exc}")
    record = {
        "record_id": Path(value).name,
        "detail": "DFIT metadata analysis completed",
        "source_fields": summary,
    }
    return SourceResult(
        "dfit",
        data=_payload(
            api_source="DFIT Digital Image Forensics Toolkit",
            api_documentation=DFIT_DOCS,
            module="dfit-toolkit==1.0.0",
            invocation="dfit metadata -i <image> -o <report.json>",
            query=Path(value).name,
            records=[record],
            total=1,
        ),
    )


def query_steg_analyzer(input_type: str, value: str) -> SourceResult:
    if input_type != "image":
        return _skip("steg-analyzer", "Steg Analyzer requires an image or file-path seed staged inside the container.")
    with tempfile.TemporaryDirectory() as temporary:
        output_dir = Path(temporary) / "steg-report"
        command = [
            "steg-analyzer",
            "analyze",
            value,
            "--metadata",
            "--ela",
            "--histogram",
            "--format",
            "json",
            "--output",
            str(output_dir),
        ]
        code, _, stderr, failure = _run_tool(command)
        if failure:
            return SourceResult("steg-analyzer", error=failure)
        if code != 0:
            return SourceResult("steg-analyzer", error=f"steg-analyzer exited with code {code}: {stderr[-300:]}")
        reports = sorted(output_dir.rglob("*.json")) if output_dir.is_dir() else []
        if not reports:
            return SourceResult("steg-analyzer", error="steg-analyzer completed without a JSON report")
        try:
            summary = _analysis_summary(reports[0])
        except (OSError, json.JSONDecodeError) as exc:
            return SourceResult("steg-analyzer", error=f"Unable to read steg-analyzer JSON report: {exc}")
    record = {
        "record_id": Path(value).name,
        "detail": "Steg Analyzer metadata, ELA and histogram analysis completed",
        "source_fields": summary,
    }
    return SourceResult(
        "steg-analyzer",
        data=_payload(
            api_source="Steg Analyzer",
            api_documentation=STEG_ANALYZER_DOCS,
            module="steg-analyzer==1.0.1",
            invocation="steg-analyzer analyze <image> --metadata --ela --histogram --format json --output <directory>",
            query=Path(value).name,
            records=[record],
            total=1,
        ),
    )


def _dropped(name: str) -> SourceResult:
    return _skip(name, UNSUPPORTED_SUB_SOURCES[name])


def _health_inventory() -> dict[str, Any]:
    entries: list[dict[str, Any]] = [
        {"source": "mapillary", "kind": "http_api", "endpoint": MAPILLARY_IMAGES_URL, "key_env": MAPILLARY_TOKEN_ENV, "key_configured": bool(os.environ.get(MAPILLARY_TOKEN_ENV, "").strip())},
        {"source": "nominatim", "kind": "http_api", "endpoint": NOMINATIM_SEARCH_URL, "key_env": None, "key_configured": False},
        {"source": "copernicus-stac", "kind": "http_api", "endpoint": COPERNICUS_STAC_ITEMS_URL, "key_env": None, "key_configured": False},
        {"source": "dfit", "kind": "local_cli", "endpoint": None, "key_env": None, "key_configured": False, "binary_present": bool(shutil.which("dfit"))},
        {"source": "steg-analyzer", "kind": "local_cli", "endpoint": None, "key_env": None, "key_configured": False, "binary_present": bool(shutil.which("steg-analyzer"))},
    ]
    entries.extend(
        {"source": name, "kind": "dropped", "endpoint": None, "key_env": None, "key_configured": False, "detail": reason}
        for name, reason in sorted(UNSUPPORTED_SUB_SOURCES.items())
    )
    return {"health": "ok", "network_used": False, "sub_sources": entries}


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        print(json.dumps(_health_inventory(), sort_keys=True), file=sys.stderr)
        print("ok")
        return 0
    if len(sys.argv) != 3:
        print("usage: runner.py <name|geolocation|image> <value>", file=sys.stderr)
        return 2
    input_type, value = sys.argv[1], sys.argv[2]
    if input_type not in {"name", "geolocation", "image"}:
        print("invalid input_type", file=sys.stderr)
        return 2
    sources = [
        query_mapillary(input_type, value),
        query_nominatim(input_type, value),
        query_copernicus_stac(input_type, value),
        query_dfit(input_type, value),
        query_steg_analyzer(input_type, value),
        *(_dropped(name) for name in sorted(UNSUPPORTED_SUB_SOURCES)),
    ]
    print(json.dumps({
        "input_type": input_type,
        "input_value": value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [source.to_dict() for source in sources],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
