"""Aletheia driver for the pinned pybdshadow package.

The driver reads one local JSON document (a UTC datetime plus a GeoJSON
FeatureCollection of building footprints with ``height`` and optional
``building_id`` properties), builds a GeoDataFrame, and calls the pinned
``pybdshadow.bdshadow_sunlight`` function. It summarises the resulting shadow
geometry (bbox, centroid, geodesic area, polygon/vertex counts) so the adapter
can ingest it.

The computation is local: no request library is called, no coordinate leaves
the container, and the capture runs under ``--network none``. The upstream
package also ships optional footprint-fetching helpers; this driver never
calls them. A shadow is geometric evidence, not a confirmed location.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PINNED_COMMIT = "e2665ee7a6527b9fb0d581bbf7d6dc2914015b02"
CHECKOUT = os.environ.get("PYBDSHADOW_CHECKOUT", "/opt/pybdshadow-src")
PIN_FILE = os.environ.get("PYBDSHADOW_PIN_FILE", "/opt/pin.txt")
MAX_BUILDINGS = 200
MAX_VERTICES = 1000
MIN_HEIGHT = 0.1
MAX_HEIGHT = 1000.0
MIN_YEAR = 1900
MAX_YEAR = 2100
MAX_INPUT_BYTES = 1_000_000
INPUT_HELP = (
    "expected a JSON object with datetime_utc=<ISO-8601 UTC> and buildings="
    "<GeoJSON FeatureCollection of Polygon features with properties.height>"
)


def _package_version() -> str:
    for name in ("pybdshadow", "PyBDShadow"):
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        except Exception:
            continue
    try:
        import pybdshadow

        return str(getattr(pybdshadow, "__version__", ""))
    except Exception:
        return ""


def _pin_file_matches() -> bool:
    try:
        text = Path(PIN_FILE).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return PINNED_COMMIT in text


def _finite_number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _parse_datetime(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("datetime_utc must be a non-empty ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid datetime_utc: {exc}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if not (MIN_YEAR <= parsed.year <= MAX_YEAR):
        raise ValueError(f"datetime_utc year must be {MIN_YEAR}..{MAX_YEAR}")
    return parsed.replace(tzinfo=None)


def _validate_document(document) -> tuple[datetime, list[dict]]:
    """Validate the input document and return plain building records.

    Deliberately does not import geopandas so the parser can be unit-tested
    without the geo stack; ``_build_frame`` performs the geometry checks.
    """
    if not isinstance(document, dict):
        raise ValueError("input must be a JSON object")
    when = _parse_datetime(document.get("datetime_utc"))
    collection = document.get("buildings")
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise ValueError("buildings must be a GeoJSON FeatureCollection")
    features = collection.get("features")
    if not isinstance(features, list) or not (1 <= len(features) <= MAX_BUILDINGS):
        raise ValueError(f"buildings.features must contain 1..{MAX_BUILDINGS} features")
    buildings: list[dict] = []
    seen: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ValueError(f"feature {index} must be an object")
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
            raise ValueError(f"feature {index} must have a Polygon geometry")
        coordinates = geometry.get("coordinates")
        if (
            not isinstance(coordinates, list)
            or len(coordinates) != 1
            or not isinstance(coordinates[0], list)
        ):
            raise ValueError(f"feature {index} must have exactly one exterior ring (no holes)")
        ring = coordinates[0]
        if not (4 <= len(ring) <= MAX_VERTICES):
            raise ValueError(f"feature {index} ring must have 4..{MAX_VERTICES} vertices")
        if ring[0] != ring[-1]:
            raise ValueError(f"feature {index} ring must be closed")
        points: list[tuple[float, float]] = []
        for point in ring:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError(f"feature {index} has an invalid coordinate")
            lon = _finite_number(point[0])
            lat = _finite_number(point[1])
            if lon is None or lat is None:
                raise ValueError(f"feature {index} has a non-finite coordinate")
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                raise ValueError(f"feature {index} coordinate is outside lon/lat bounds")
            points.append((lon, lat))
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            raise ValueError(f"feature {index} properties must be an object")
        height = _finite_number(properties.get("height"))
        if height is None or not (MIN_HEIGHT <= height <= MAX_HEIGHT):
            raise ValueError(
                f"feature {index} properties.height must be {MIN_HEIGHT}..{MAX_HEIGHT}"
            )
        building_id = properties.get("building_id", f"b{index + 1}")
        if not isinstance(building_id, str) or not (1 <= len(building_id) <= 64):
            raise ValueError(f"feature {index} building_id must be a 1..64 character string")
        if building_id in seen:
            raise ValueError(f"duplicate building_id: {building_id}")
        seen.add(building_id)
        buildings.append({"building_id": building_id, "height": height, "ring": points})
    return when, buildings


def _build_frame(buildings: list[dict]):
    import geopandas as gpd
    from shapely.geometry import Polygon

    geometries = []
    for building in buildings:
        polygon = Polygon(building["ring"])
        if polygon.is_empty or not polygon.is_valid:
            raise ValueError(f"building {building['building_id']} is not a valid polygon")
        geometries.append(polygon)
    return gpd.GeoDataFrame(
        {
            "building_id": [item["building_id"] for item in buildings],
            "height": [item["height"] for item in buildings],
        },
        geometry=geometries,
        crs="EPSG:4326",
    )


def _summarise(shadows) -> list[dict]:
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    summaries: list[dict] = []
    for _, row in shadows.iterrows():
        geometry = row.get("geometry")
        if geometry is None or geometry.is_empty:
            continue
        if geometry.geom_type == "Polygon":
            polygons = [geometry]
        elif geometry.geom_type.startswith("Multi"):
            polygons = [item for item in geometry.geoms if item.geom_type == "Polygon"]
        else:
            polygons = []
        polygons = [item for item in polygons if not item.is_empty]
        if not polygons:
            continue
        centroid = geometry.centroid
        area, _ = geod.geometry_area_perimeter(geometry)
        summaries.append(
            {
                "building_id": str(row.get("building_id", "")),
                "bbox": [float(value) for value in geometry.bounds],
                "centroid": [float(centroid.x), float(centroid.y)],
                "shadow_area_m2": round(abs(area), 3),
                "polygons": len(polygons),
                "vertices": sum(len(item.exterior.coords) for item in polygons),
            }
        )
    return summaries


def _compute(when: datetime, frame, public: dict) -> dict:
    import pybdshadow

    try:
        shadows = pybdshadow.bdshadow_sunlight(
            frame, when, height="height", roof=False, include_building=True
        )
    except ValueError as exc:
        message = str(exc)
        if "sunrise" in message.lower() or "sunset" in message.lower():
            return {
                "source": "pybdshadow",
                "status": "no_sunlight",
                "pinned_commit": PINNED_COMMIT,
                "input": public,
                "thresholds": _thresholds(),
                "shadows": [],
                "shadows_total": 0,
                "error": message,
            }
        raise
    summaries = _summarise(shadows)
    return {
        "source": "pybdshadow",
        "status": "ok" if summaries else "no_candidates",
        "pinned_commit": PINNED_COMMIT,
        "input": public,
        "thresholds": _thresholds(),
        "shadows": summaries,
        "shadows_total": len(summaries),
    }


def _thresholds() -> dict:
    return {
        "max_buildings": MAX_BUILDINGS,
        "max_vertices": MAX_VERTICES,
        "height_range_m": [MIN_HEIGHT, MAX_HEIGHT],
        "max_input_bytes": MAX_INPUT_BYTES,
    }


def _public_input(when: datetime, buildings: list[dict]) -> dict:
    return {
        "datetime_utc": when.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "buildings_total": len(buildings),
    }


def _health() -> int:
    details = {
        "pinned_commit": PINNED_COMMIT,
        "checkout": CHECKOUT,
        "pin_file": _pin_file_matches(),
        "package_version": _package_version(),
        "package_import": False,
        "network_required": False,
    }
    try:
        import geopandas
        import pybdshadow  # noqa: F401
        import pyproj
        import shapely

        details["package_import"] = True
        details["geopandas_version"] = str(getattr(geopandas, "__version__", ""))
        details["pyproj_version"] = str(getattr(pyproj, "__version__", ""))
        details["shapely_version"] = str(getattr(shapely, "__version__", ""))
    except Exception as exc:
        details["import_error"] = f"{type(exc).__name__}: {exc}"
    ok = details["pin_file"] and bool(details["package_version"]) and details["package_import"]
    print("ok" if ok else "fail")
    print(json.dumps(details), file=sys.stderr)
    return 0 if ok else 1


def _selftest() -> int:
    checks: list[dict] = []

    def check(name, func) -> None:
        try:
            ok, detail = func()
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    def document(height=10.0, when="2024-06-01T12:00:00Z", building_id="b1", ring=None):
        if ring is None:
            ring = [
                [0.0, 0.0],
                [0.0002, 0.0],
                [0.0002, 0.0002],
                [0.0, 0.0002],
                [0.0, 0.0],
            ]
        return {
            "datetime_utc": when,
            "buildings": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"building_id": building_id, "height": height},
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                    }
                ],
            },
        }

    def validation() -> tuple[bool, str]:
        when, buildings = _validate_document(document())
        ok = (
            when.year == 2024
            and len(buildings) == 1
            and buildings[0]["height"] == 10.0
            and buildings[0]["building_id"] == "b1"
        )
        bad = [
            document(height=0),
            document(ring=[[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]),
            document(ring=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]),
        ]
        ok = ok and all(
            _raises(lambda item=item: _validate_document(item)) for item in bad
        )
        return ok, "bounded document validation"

    def computation() -> tuple[bool, str]:
        when, buildings = _validate_document(document())
        frame = _build_frame(buildings)
        payload = _compute(when, frame, _public_input(when, buildings))
        shadows = payload.get("shadows") or []
        ok = (
            payload.get("status") == "ok"
            and len(shadows) == 1
            and shadows[0]["shadow_area_m2"] > 0
            and shadows[0]["polygons"] >= 1
        )
        return ok, f"status={payload.get('status')} shadows={len(shadows)}"

    def night() -> tuple[bool, str]:
        when, buildings = _validate_document(
            document(when="2024-06-01T00:00:00Z")
        )
        frame = _build_frame(buildings)
        payload = _compute(when, frame, _public_input(when, buildings))
        return payload.get("status") == "no_sunlight", str(payload.get("status"))

    def limits() -> tuple[bool, str]:
        many = {
            "datetime_utc": "2024-06-01T12:00:00Z",
            "buildings": {
                "type": "FeatureCollection",
                "features": document()["buildings"]["features"] * (MAX_BUILDINGS + 1),
            },
        }
        duplicate = {
            "datetime_utc": "2024-06-01T12:00:00Z",
            "buildings": {
                "type": "FeatureCollection",
                "features": document()["buildings"]["features"]
                + document(height=20.0, building_id="b1")["buildings"]["features"],
            },
        }
        return (
            _raises(lambda: _validate_document(many))
            and _raises(lambda: _validate_document(duplicate)),
            "building-count and duplicate-id bounds",
        )

    def offset() -> tuple[bool, str]:
        when, _ = _validate_document(document(when="2024-06-01T14:00:00+02:00"))
        naive, _ = _validate_document(document(when="2024-06-01T12:00:00"))
        return when.hour == 12 and naive.hour == 12, f"normalized_hour={when.hour}"

    check("pin_file", lambda: (_pin_file_matches(), PIN_FILE))
    check("package_import", lambda: (bool(_package_version()), _package_version()))
    check("document_validation", validation)
    check("datetime_normalization", offset)
    check("limits", limits)
    check("computation", computation)
    check("night_rejection", night)
    check("output_contract", lambda: (_thresholds()["max_buildings"] == MAX_BUILDINGS, "bounded summary"))
    ok = all(item["ok"] for item in checks)
    print(json.dumps({"pybdshadow_selftest": "ok" if ok else "fail", "checks": checks}, indent=2))
    return 0 if ok else 1


def _raises(func) -> bool:
    try:
        func()
    except ValueError:
        return True
    except Exception:
        return False
    return False


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--health" in arguments:
        return _health()
    if "--selftest" in arguments:
        return _selftest()
    if len(arguments) != 1:
        print(json.dumps({"source": "pybdshadow", "status": "invalid_target", "error": INPUT_HELP}))
        return 2
    path = Path(arguments[0])
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError(f"input exceeds {MAX_INPUT_BYTES} bytes")
        document = json.loads(raw.decode("utf-8"))
        when, buildings = _validate_document(document)
        frame = _build_frame(buildings)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "source": "pybdshadow",
                    "status": "invalid_target",
                    "error": f"{exc}",
                    "help": INPUT_HELP,
                }
            )
        )
        return 2
    try:
        payload = _compute(when, frame, _public_input(when, buildings))
    except Exception as exc:  # pragma: no cover - image only
        print(
            json.dumps(
                {
                    "source": "pybdshadow",
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        )
        return 3
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
