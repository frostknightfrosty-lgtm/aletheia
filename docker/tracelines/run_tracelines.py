#!/usr/bin/env python3
"""Aletheia driver for the pinned `tracelines` package (street-level coverage).

Only the documented, keyless-or-free-token providers are invoked: Mapillary
(sequence vector tiles; free token from ``MAPILLARY_TOKEN``) and KartaView
(documented bbox sequence API; keyless). The Google provider is excluded
structurally — the package is installed without ``streetlevel`` and the driver
refuses to run if the Google provider reports itself available or the settings
name it.

Input is exactly one point (``--point LAT,LON``, optionally ``--radius`` metres,
capped) which becomes a small bounding box. Output is a single JSON document
with per-source status and summarized coverage segments; no coverage geometry
is written to disk or redistributed.

Exit codes: 0 ok/empty/blocked, 1 error, 2 usage/invalid target, 3 hard deadline.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import math
import os
import sys
import threading
from pathlib import Path

CHECKOUT = os.environ.get("TRACELINES_CHECKOUT", "/opt/tracelines")
PINNED_COMMIT = "99257f0519b30ce7d890db25252f6cf440fa102e"
HONEST_UA = "Aletheia/0.9.0 (tracelines)"

DEFAULT_RADIUS_M = 300.0
MAX_RADIUS_M = 300.0
GATHER_TIMEOUT_SECONDS = 120.0
HARD_DEADLINE_SECONDS = 180.0
MAX_SEGMENTS_PER_SOURCE = 40

SOURCES = ("mapillary", "kartaview")
EXCLUDED_PARTS = ("google", "nearest", "historical", "npm", "proxy", "gui")
MAPILLARY_KEY_ENV = "MAPILLARY_TOKEN"

BLOCKED_MARKERS = ("401", "403", "429", "forbidden", "too many requests", "cloudflare", "turnstile")
TLS_FORBIDDEN_MARKERS = (
    "ssl=false",
    "verify_ssl=false",
    "ssl_verify=false",
    "cert_none",
    "check_hostname=false",
    "check_hostname = false",
)

ATTRIBUTION = {
    "mapillary": "© Mapillary contributors, CC-BY-SA 4.0",
    "kartaview": "© KartaView contributors, CC-BY-SA 4.0",
}

_REAL_STDOUT = sys.stdout


def _pin_file_matches() -> bool:
    try:
        with open(os.path.join(CHECKOUT, "PINNED_COMMIT"), "r", encoding="utf-8") as handle:
            return handle.read().strip() == PINNED_COMMIT
    except OSError:
        return False


def _package_version() -> str:
    import tracelines

    return str(getattr(tracelines, "__version__", "") or "unknown")


def _streetlevel_present() -> bool:
    return importlib.util.find_spec("streetlevel") is not None


def _tls_static() -> tuple[bool, str]:
    """Fail closed if the pinned package contains any TLS relaxation."""
    try:
        import tracelines

        root = Path(tracelines.__file__).resolve().parent
    except Exception as exc:
        return False, f"package not importable: {type(exc).__name__}: {exc}"
    hits: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        for marker in TLS_FORBIDDEN_MARKERS:
            if marker in text:
                hits.append(f"{path.name}: {marker}")
    if hits:
        return False, "; ".join(hits[:5])
    return True, "no TLS relaxation found in the pinned sources"


def _settings(radius_m: float = DEFAULT_RADIUS_M):
    from tracelines import Settings

    return Settings(
        concurrency=4,
        timeout=25.0,
        max_retries=1,
        zoom_mapillary=14,
        min_run=2,
        include_third_party=False,
        include_trekker=False,
        precision=False,
        snap=False,
        dedupe=False,
        cache_enabled=False,
        user_agent=HONEST_UA,
        mapillary_token=os.environ.get(MAPILLARY_KEY_ENV) or None,
    )


def _load_providers() -> dict:
    from tracelines.providers import get_provider

    return {name: get_provider(name) for name in SOURCES}


def _parse_point(value: str) -> tuple[float, float] | None:
    parts = value.split(",")
    if len(parts) != 2:
        return None
    try:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
    except ValueError:
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _bbox_for_point(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    radius = max(1.0, min(float(radius_m), MAX_RADIUS_M))
    dlat = radius / 111_320.0
    dlon = radius / (111_320.0 * max(0.05, math.cos(math.radians(lat))))
    west = max(-180.0, lon - dlon)
    east = min(180.0, lon + dlon)
    south = max(-90.0, lat - dlat)
    north = min(90.0, lat + dlat)
    return tuple(round(value, 6) for value in (west, south, east, north))


def _parse_args(argv: list[str]):
    point = None
    radius = DEFAULT_RADIUS_M
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--point" and index + 1 < len(argv):
            point = argv[index + 1]
            index += 2
            continue
        if token == "--radius" and index + 1 < len(argv):
            try:
                radius = float(argv[index + 1])
            except ValueError:
                return None
            if not math.isfinite(radius) or radius <= 0:
                return None
            index += 2
            continue
        return None
    if point is None:
        return None
    return point, min(radius, MAX_RADIUS_M)


def _looks_blocked(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in BLOCKED_MARKERS)


def _source_status(stats, segments: list) -> tuple[str, str]:
    if not isinstance(stats, dict):
        stats = {}
    for key in ("skipped", "unavailable"):
        if key in stats:
            return "skipped", str(stats[key])
    if "error" in stats:
        reason = str(stats["error"])
        return ("blocked" if _looks_blocked(reason) else "error"), reason
    if not segments:
        if stats.get("note"):
            reason = str(stats["note"])
            return ("blocked" if _looks_blocked(reason) else "error"), reason
        failed = stats.get("tiles_failed")
        if isinstance(failed, int) and failed > 0:
            return "error", f"{failed} Mapillary tile request(s) failed"
        return "empty", ""
    return "ok", ""


def _derive_run_status(statuses: dict) -> str:
    values = [status for status in statuses.values() if status != "skipped"]
    if not values:
        return "empty"
    if "ok" in values:
        return "ok"
    if "empty" in values:
        return "empty"
    if all(status == "blocked" for status in values):
        return "blocked"
    return "error"


def _summarize_segment(segment) -> dict:
    coords = list(getattr(segment, "coords", None) or [])
    source = getattr(segment, "source", None)
    source_name = getattr(source, "value", str(source))
    centroid = None
    if coords:
        centroid = [
            round(sum(point[0] for point in coords) / len(coords), 6),
            round(sum(point[1] for point in coords) / len(coords), 6),
        ]
    return {
        "id": str(getattr(segment, "id", "") or ""),
        "source": source_name,
        "length_m": round(float(getattr(segment, "length_m", 0.0) or 0.0), 2),
        "n_points": int(getattr(segment, "n_points", len(coords)) or 0),
        "capture_date": getattr(segment, "capture_date", None),
        "is_pano": getattr(segment, "is_pano", None),
        "centroid": centroid,
        "start": coords[0] if coords else None,
        "end": coords[-1] if coords else None,
        "attribution": ATTRIBUTION.get(source_name, ""),
    }


def _normalization_ok() -> bool:
    try:
        from tracelines.models import CoverageSegment, Source, haversine_m, line_length_m
        from tracelines.providers.kartaview import parse_sequences

        if haversine_m(0.0, 0.0, 0.0, 0.0) != 0.0:
            return False
        segment = CoverageSegment(coords=[(0.0, 0.0), (0.0, 0.001)], source=Source.KARTAVIEW)
        if not 100.0 <= segment.length_m <= 120.0:
            return False
        if not 100.0 <= line_length_m([(0.0, 0.0), (0.0, 0.001)]) <= 120.0:
            return False
        payload = {
            "result": {
                "items": [
                    {
                        "id": 7,
                        "track": [[26.10, 44.44], [26.11, 44.44], [26.12, 44.44]],
                    }
                ]
            }
        }
        segments = parse_sequences(payload, 2)
        summary = _summarize_segment(segments[0])
        return (
            len(segments) == 1
            and segments[0].n_points == 3
            and segments[0].source == Source.KARTAVIEW
            and summary["source"] == "kartaview"
            and summary["length_m"] > 0
            and summary["attribution"].startswith("© KartaView")
        )
    except Exception:
        return False


def health() -> int:
    details = {"pinned_commit": PINNED_COMMIT}
    try:
        details["package_version"] = _package_version()
        settings = _settings()
        details["user_agent"] = settings.user_agent
        details["cache_enabled"] = bool(settings.cache_enabled)
        details["max_retries"] = int(settings.max_retries)
        details["streetlevel_installed"] = _streetlevel_present()
        tls_ok, tls_detail = _tls_static()
        details["tls_static"] = tls_ok
        details["pin_file"] = _pin_file_matches()
        providers = _load_providers()
        details["provider_bindings"] = sorted(providers)
        details["provider_available"] = {
            name: bool(provider.available()[0]) for name, provider in providers.items()
        }
    except Exception as exc:
        sys.stderr.write(f"health check failed: {type(exc).__name__}: {exc}\n")
        print("error")
        return 1
    sys.stderr.write(json.dumps(details, ensure_ascii=False) + "\n")
    if not details["pin_file"]:
        print("error")
        return 1
    if details["streetlevel_installed"]:
        print("error")
        return 1
    if not details["tls_static"]:
        print("error")
        return 1
    if not details["provider_available"].get("mapillary") or not details["provider_available"].get("kartaview"):
        print("error")
        return 1
    if details["user_agent"] != HONEST_UA or details["cache_enabled"] or details["max_retries"] != 1:
        print("error")
        return 1
    print("ok")
    return 0


def selftest(loader=None, ua_probe=None, package_probe=None, streetlevel_probe=None, tls_probe=None) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    report = {
        "tracelines_selftest": "ok",
        "pinned_commit": PINNED_COMMIT,
        "checks": checks,
    }

    check("pin_file", _pin_file_matches())

    version = "unavailable"
    try:
        version = (package_probe or _package_version)()
        check("package_import", bool(version) and version != "unavailable", str(version))
    except Exception as exc:
        check("package_import", False, f"{type(exc).__name__}: {exc}")
    report["package_version"] = version

    providers: dict = {}
    try:
        providers = (loader or _load_providers)()
        check(
            "provider_construction",
            set(SOURCES) <= set(providers) and len(providers) == len(SOURCES),
            f"providers={sorted(providers)}",
        )
    except Exception as exc:
        check("provider_construction", False, f"{type(exc).__name__}: {exc}")
    report["provider_bindings"] = len(providers)

    settings = _settings()
    agent = ""
    try:
        agent = str((ua_probe or (lambda value: value.user_agent))(settings) or "")
    except Exception:
        agent = ""
    check("ua_honest", "Aletheia/0.9.0" in agent, agent)
    check(
        "no_retries_no_cache",
        settings.max_retries == 1 and settings.cache_enabled is False and settings.dedupe is False,
        f"max_retries={settings.max_retries} cache_enabled={settings.cache_enabled} dedupe={settings.dedupe}",
    )

    try:
        present = bool((streetlevel_probe or _streetlevel_present)())
    except Exception:
        present = True
    check("google_absent", (not present) and "google" not in SOURCES, f"streetlevel_installed={present}")

    if tls_probe is not None:
        tls_ok, tls_detail = tls_probe()
    else:
        tls_ok, tls_detail = _tls_static()
    check("tls_static", bool(tls_ok), str(tls_detail))

    sample = _parse_point("37.7749,-122.4194")
    bbox = _bbox_for_point(37.7749, -122.4194, DEFAULT_RADIUS_M) if sample else None
    check(
        "target_validation",
        sample == (37.7749, -122.4194)
        and _parse_point("91,0") is None
        and _parse_point("nan,0") is None
        and _parse_point("37.7") is None
        and bbox is not None
        and bbox[0] < -122.4194 < bbox[2]
        and bbox[1] < 37.7749 < bbox[3],
    )

    check(
        "source_scoping",
        SOURCES == ("mapillary", "kartaview")
        and "google" not in SOURCES
        and set(EXCLUDED_PARTS) >= {"google", "nearest", "historical"},
    )

    check("normalization", _normalization_ok())

    if not all(item["ok"] for item in checks):
        report["tracelines_selftest"] = "fail"
    return report


def _deadline_abort(state):
    document = {
        "source": "tracelines",
        "sub_source": "street_view_coverage",
        "pinned_commit": PINNED_COMMIT,
        "target": state.get("target"),
        "bbox": state.get("bbox"),
        "status": "error",
        "deadline_exceeded": True,
        "stage": state.get("stage"),
        "sources": {},
        "error": f"hard deadline of {int(HARD_DEADLINE_SECONDS)}s exceeded",
    }
    _REAL_STDOUT.write(json.dumps(document, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()
    os._exit(3)


def main(argv: list[str]) -> int:
    if argv == ["--health"]:
        return health()
    if argv == ["--selftest"]:
        report = selftest()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["tracelines_selftest"] == "ok" else 1

    parsed = _parse_args(argv)
    if parsed is None:
        sys.stderr.write(
            "usage: run_tracelines.py --point LAT,LON [--radius METERS] | --health | --selftest\n"
        )
        return 2
    raw_target, radius = parsed
    point = _parse_point(raw_target)

    document = {
        "source": "tracelines",
        "sub_source": "street_view_coverage",
        "pinned_commit": PINNED_COMMIT,
        "package_version": "unavailable",
        "user_agent": HONEST_UA,
        "target": raw_target,
        "bbox": None,
        "radius_m": radius,
        "requested_sources": list(SOURCES),
        "status": "error",
        "sources": {},
        "fused_count": 0,
    }

    if point is None:
        document["status"] = "invalid_target"
        document["error"] = "expected --point LAT,LON with lat in [-90,90] and lon in [-180,180]"
        print(json.dumps(document, ensure_ascii=False))
        return 2
    latitude, longitude = point
    bbox = _bbox_for_point(latitude, longitude, radius)
    document["bbox"] = list(bbox)

    try:
        settings = _settings(radius)
        document["package_version"] = _package_version()
    except Exception as exc:
        document["error"] = f"driver setup failed: {type(exc).__name__}: {exc}"
        print(json.dumps(document, ensure_ascii=False))
        return 1

    if _streetlevel_present():
        document["error"] = "streetlevel is installed; refusing to run (Google path must stay excluded)"
        print(json.dumps(document, ensure_ascii=False))
        return 1
    if settings.user_agent != HONEST_UA:
        document["error"] = "honest user agent is not in effect; refusing to run (fail closed)"
        print(json.dumps(document, ensure_ascii=False))
        return 1
    tls_ok, tls_detail = _tls_static()
    if not tls_ok:
        document["error"] = f"pinned sources relax TLS; refusing to run (fail closed): {tls_detail}"
        print(json.dumps(document, ensure_ascii=False))
        return 1

    from tracelines.config import BBox
    from tracelines.pipeline import extract_async

    state = {"target": raw_target, "bbox": list(bbox), "stage": "providers"}
    watchdog = threading.Timer(HARD_DEADLINE_SECONDS, _deadline_abort, args=(state,))
    watchdog.daemon = True
    watchdog.start()
    try:
        segments, meta = asyncio.run(
            asyncio.wait_for(
                extract_async(BBox(*bbox), list(SOURCES), settings),
                GATHER_TIMEOUT_SECONDS,
            )
        )
        stats = meta.get("by_source_stats", {}) if isinstance(meta, dict) else {}
        by_source: dict = {name: [] for name in SOURCES}
        for segment in segments:
            source = getattr(getattr(segment, "source", None), "value", str(getattr(segment, "source", "")))
            by_source.setdefault(source, []).append(segment)
        statuses: dict = {}
        sources_doc: dict = {}
        for name in SOURCES:
            source_segments = by_source.get(name, [])
            status, reason = _source_status(stats.get(name, {}), source_segments)
            statuses[name] = status
            summarized = [_summarize_segment(segment) for segment in source_segments[:MAX_SEGMENTS_PER_SOURCE]]
            sources_doc[name] = {
                "status": status,
                "reason": reason,
                "stats": stats.get(name, {}),
                "segments": summarized,
                "segments_total": len(source_segments),
                "segments_truncated": len(source_segments) > len(summarized),
            }
        document["sources"] = sources_doc
        document["fused_count"] = len(segments)
        document["status"] = _derive_run_status(statuses)
    except asyncio.TimeoutError:
        document["status"] = "error"
        document["error"] = f"gather timeout of {int(GATHER_TIMEOUT_SECONDS)}s exceeded"
    except Exception as exc:
        document["status"] = "error"
        document["error"] = f"driver run failed: {type(exc).__name__}: {exc}"
    finally:
        watchdog.cancel()

    print(json.dumps(document, ensure_ascii=False))
    return 0 if document["status"] in {"ok", "empty", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
