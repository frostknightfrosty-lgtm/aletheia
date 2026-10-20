"""Aletheia driver for the pinned Bellingcat ShadowFinder package.

The driver is offline by design: it imports the pinned library, loads the
timezone grid shipped in the upstream checkout, and computes coarse candidate
regions for one shadow observation (object height, shadow length, UTC
datetime). No request library is used and no coordinate is transmitted.

The upstream CLI only renders a PNG; this driver calls the library and
summarises the likelihood grid into bounded regions so the adapter can ingest
it. A candidate region is a possibility band from solar geometry, not a
confirmed location.
"""
from __future__ import annotations

import importlib.metadata
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PINNED_COMMIT = "215485abd5a46a9b98c4ba0fbfce7df6b6bb1be8"
CHECKOUT = os.environ.get("SHADOWFINDER_CHECKOUT", "/opt/shadowfinder")
GRID_PATH = os.environ.get("SHADOWFINDER_GRID", "/opt/shadowfinder/timezone_grid.json")
DEFAULT_TOLERANCE = 0.10
MAX_TOLERANCE = 0.50
DEFAULT_BIN_DEG = 1.0
MIN_BIN_DEG = 0.25
MAX_BIN_DEG = 5.0
DEFAULT_MAX_REGIONS = 20
MAX_REGIONS_LIMIT = 50
DEFAULT_STEP = 1
MAX_STEP = 4
MIN_YEAR = 1900
MAX_YEAR = 2100
OBSERVATION_HELP = (
    "expected --observation height=<metres>;shadow=<metres>;"
    "datetime=<UTC ISO-8601>"
)


def _pin_file_matches() -> bool:
    try:
        text = Path(CHECKOUT, "PINNED_COMMIT").read_text(encoding="utf-8")
    except OSError:
        return False
    return text.strip() == PINNED_COMMIT


def _package_version() -> str:
    for name in ("ShadowFinder", "shadowfinder"):
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        except Exception:
            continue
    return ""


def _parse_datetime(text: str) -> datetime | None:
    """Parse an ISO-8601 datetime and return a naive UTC datetime.

    A value without an offset is interpreted as UTC, matching the driver's
    documented observation format. Date-only values are rejected so the time
    of day can never be silently assumed.
    """
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw or "T" not in raw.upper():
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if not (MIN_YEAR <= parsed.year <= MAX_YEAR):
        return None
    return parsed.replace(tzinfo=None)


def _parse_observation(raw: str) -> tuple[dict, datetime] | None:
    """Parse ``height=..;shadow=..;datetime=..`` into public fields plus a UTC datetime."""
    if not isinstance(raw, str):
        return None
    parts: dict[str, str] = {}
    for chunk in raw.replace("&", ";").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            return None
        key, value = chunk.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in parts or key not in {"height", "shadow", "datetime"}:
            return None
        parts[key] = value
    if set(parts) != {"height", "shadow", "datetime"}:
        return None
    try:
        height = float(parts["height"])
        shadow = float(parts["shadow"])
    except ValueError:
        return None
    if not (math.isfinite(height) and math.isfinite(shadow)) or height <= 0 or shadow <= 0:
        return None
    when = _parse_datetime(parts["datetime"])
    if when is None:
        return None
    public = {
        "height_m": height,
        "shadow_length_m": shadow,
        "datetime_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return public, when


def _parse_args(argv: list[str]) -> dict | None:
    options = {
        "observation": None,
        "tolerance": DEFAULT_TOLERANCE,
        "bin_deg": DEFAULT_BIN_DEG,
        "max_regions": DEFAULT_MAX_REGIONS,
        "step": DEFAULT_STEP,
    }
    index = 0
    seen: set[str] = set()
    while index < len(argv):
        flag = argv[index]
        if flag not in {"--observation", "--tolerance", "--bin-deg", "--max-regions", "--step"}:
            return None
        if flag in seen or index + 1 >= len(argv):
            return None
        seen.add(flag)
        value = argv[index + 1]
        if flag == "--observation":
            options["observation"] = value
        elif flag == "--tolerance":
            try:
                parsed = float(value)
            except ValueError:
                return None
            if not math.isfinite(parsed) or not (0 < parsed <= MAX_TOLERANCE):
                return None
            options["tolerance"] = parsed
        elif flag == "--bin-deg":
            try:
                parsed = float(value)
            except ValueError:
                return None
            if not math.isfinite(parsed) or not (MIN_BIN_DEG <= parsed <= MAX_BIN_DEG):
                return None
            options["bin_deg"] = parsed
        elif flag == "--max-regions":
            try:
                parsed = int(value)
            except ValueError:
                return None
            if not (1 <= parsed <= MAX_REGIONS_LIMIT):
                return None
            options["max_regions"] = parsed
        elif flag == "--step":
            try:
                parsed = int(value)
            except ValueError:
                return None
            if not (1 <= parsed <= MAX_STEP):
                return None
            options["step"] = parsed
        index += 2
    if not options["observation"]:
        return None
    return options


def _bin_candidates(
    lats,
    lons,
    likelihoods,
    tolerance: float,
    bin_deg: float,
    max_regions: int,
):
    """Summarise matching grid cells into ranked, bounded bins.

    Pure standard-library code so the helper is testable without numpy or the
    upstream package. ``lats``/``lons``/``likelihoods`` are 2-D row-major
    sequences of the same shape.
    """
    bins: dict[tuple[int, int], dict] = {}
    matching = 0
    evaluated = 0
    for row, lat_row in enumerate(lats):
        lon_row = lons[row]
        likelihood_row = likelihoods[row]
        for column, lat in enumerate(lat_row):
            try:
                likelihood = float(likelihood_row[column])
            except (TypeError, ValueError, IndexError):
                continue
            if not math.isfinite(likelihood):
                continue
            evaluated += 1
            if abs(likelihood) > tolerance:
                continue
            matching += 1
            lat_value = float(lat)
            lon_value = float(lon_row[column])
            key = (math.floor(lat_value / bin_deg), math.floor(lon_value / bin_deg))
            entry = bins.get(key)
            if entry is None:
                entry = {
                    "count": 0,
                    "sum_lat": 0.0,
                    "sum_lon": 0.0,
                    "best_abs": abs(likelihood),
                    "best_likelihood": likelihood,
                    "best_lat": lat_value,
                    "best_lon": lon_value,
                }
                bins[key] = entry
            entry["count"] += 1
            entry["sum_lat"] += lat_value
            entry["sum_lon"] += lon_value
            if abs(likelihood) < entry["best_abs"]:
                entry["best_abs"] = abs(likelihood)
                entry["best_likelihood"] = likelihood
                entry["best_lat"] = lat_value
                entry["best_lon"] = lon_value

    ordered = sorted(
        bins.items(),
        key=lambda item: (item[1]["best_abs"], -item[1]["count"], item[0][0], item[0][1]),
    )
    candidates = []
    for rank, (key, entry) in enumerate(ordered[:max_regions], start=1):
        lat0 = max(-90.0, key[0] * bin_deg)
        lon0 = max(-180.0, key[1] * bin_deg)
        lat1 = min(90.0, lat0 + bin_deg)
        lon1 = min(180.0, lon0 + bin_deg)
        candidates.append(
            {
                "rank": rank,
                "bbox": [lat0, lon0, lat1, lon1],
                "centroid": [
                    round(entry["sum_lat"] / entry["count"], 6),
                    round(entry["sum_lon"] / entry["count"], 6),
                ],
                "best_cell": {
                    "lat": round(entry["best_lat"], 6),
                    "lon": round(entry["best_lon"], 6),
                    "relative_difference": round(entry["best_likelihood"], 6),
                },
                "cell_count": entry["count"],
            }
        )
    return candidates, matching, len(bins), evaluated


def _network_imports() -> list[str]:
    """Return outbound-client imports found in the pinned package, if any."""
    try:
        import shadowfinder
    except Exception:
        return ["package not importable"]
    root = Path(shadowfinder.__file__).resolve().parent
    pattern = re.compile(
        r"^\s*(?:import|from)\s+(requests|aiohttp|httpx|urllib\.request|http\.client|socket)\b",
        re.MULTILINE,
    )
    hits = []
    for path in sorted(root.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in pattern.finditer(text):
            hits.append(f"{path.name}:{match.group(1)}")
    return hits


def _run(public: dict, when: datetime, options: dict) -> dict:
    import numpy as np
    from shadowfinder import ShadowFinder

    started = time.monotonic()
    finder = ShadowFinder(
        object_height=public["height_m"],
        shadow_length=public["shadow_length_m"],
        date_time=when,
        time_format="utc",
    )
    finder.load_timezone_grid(options["grid_path"])
    resolution = float(finder.angular_resolution)
    cells_total = int(np.asarray(finder.lats).size)
    if options["step"] > 1:
        shape = finder.lats.shape
        step = options["step"]
        finder.lats = finder.lats[::step, ::step]
        finder.lons = finder.lons[::step, ::step]
        finder.timezones = (
            np.asarray(finder.timezones).reshape(shape)[::step, ::step].ravel()
        )
    finder.find_shadows()
    candidates, matching, regions_total, evaluated = _bin_candidates(
        finder.lats,
        finder.lons,
        finder.location_likelihoods,
        options["tolerance"],
        options["bin_deg"],
        options["max_regions"],
    )
    elapsed = time.monotonic() - started
    return {
        "source": "shadowfinder",
        "version": _package_version(),
        "pinned_commit": PINNED_COMMIT,
        "status": "ok" if candidates else "no_candidates",
        "observation": public,
        "grid": {
            "angular_resolution_deg": resolution,
            "cells_total": cells_total,
            "cells_sampled": int(np.asarray(finder.lats).size),
            "cells_evaluated": evaluated,
            "cells_matching": matching,
            "sampling_step": options["step"],
        },
        "thresholds": {
            "tolerance": options["tolerance"],
            "bin_deg": options["bin_deg"],
            "max_regions": options["max_regions"],
        },
        "candidates": candidates,
        "regions_total": regions_total,
        "truncated": regions_total > len(candidates),
        "attribution": (
            "ShadowFinder (Bellingcat), MIT; solar position via suncalc; "
            "timezone grid shipped with the pinned checkout."
        ),
        "network": False,
        "elapsed_seconds": round(elapsed, 3),
    }


def _health() -> int:
    details = {
        "pinned_commit": PINNED_COMMIT,
        "checkout": CHECKOUT,
        "pin_file": _pin_file_matches(),
        "grid_file": os.path.isfile(GRID_PATH),
        "package_version": _package_version(),
        "network_imports": [],
    }
    ok = details["pin_file"] and details["grid_file"] and bool(details["package_version"])
    try:
        from shadowfinder import ShadowFinder  # noqa: F401

        details["package_import"] = True
        details["network_imports"] = _network_imports()
        if details["network_imports"]:
            ok = False
    except Exception as exc:  # pragma: no cover - exercised in the image only
        details["package_import"] = False
        details["error"] = f"{type(exc).__name__}: {exc}"
        ok = False
    if details["grid_file"]:
        try:
            grid = json.loads(Path(GRID_PATH).read_text(encoding="utf-8"))
            details["grid_resolution_deg"] = grid.get("angular_resolution")
            details["grid_cells"] = len(grid.get("timezones") or [])
            if not details["grid_cells"]:
                ok = False
        except (OSError, ValueError) as exc:
            details["error"] = f"grid unreadable: {type(exc).__name__}: {exc}"
            ok = False
    print("ok" if ok else "error")
    print(json.dumps(details, ensure_ascii=False), file=sys.stderr)
    return 0 if ok else 1


def _selftest() -> int:
    checks: list[dict] = []

    def check(name: str, func) -> None:
        try:
            result = func()
        except Exception as exc:  # pragma: no cover - image only
            checks.append({"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
            return
        if isinstance(result, tuple):
            ok, detail = result
        else:
            ok, detail = bool(result), ""
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def computation() -> tuple[bool, str]:
        import numpy as np
        from shadowfinder import ShadowFinder

        when = datetime(2024, 6, 1, 12, 0, 0)
        finder = ShadowFinder(
            object_height=10.0,
            shadow_length=5.0,
            date_time=when,
            time_format="utc",
        )
        finder.load_timezone_grid(GRID_PATH)
        lats = finder.lats
        lons = finder.lons
        mask = (lats >= 50.5) & (lats <= 52.5) & (lons >= -1.0) & (lons <= 1.0)
        rows = np.where(mask.any(axis=1))[0]
        columns = np.where(mask.any(axis=0))[0]
        if not len(rows) or not len(columns):
            return False, "no grid cells near the selftest point"
        shape = finder.lats.shape
        r0, c0 = int(rows[0]), int(columns[0])
        finder.lats = finder.lats[r0 : r0 + 3, c0 : c0 + 3]
        finder.lons = finder.lons[r0 : r0 + 3, c0 : c0 + 3]
        finder.timezones = np.asarray(finder.timezones).reshape(shape)[
            r0 : r0 + 3, c0 : c0 + 3
        ].ravel()
        finder.find_shadows()
        finite = int(np.isfinite(finder.location_likelihoods).sum())
        return finite > 0, f"finite_cells={finite}"

    def binning() -> tuple[bool, str]:
        candidates, matching, regions, evaluated = _bin_candidates(
            [[10.0, 10.0], [11.0, 11.0]],
            [[20.0, 21.0], [20.0, 21.0]],
            [[0.01, 0.2], [0.05, 0.5]],
            tolerance=0.1,
            bin_deg=1.0,
            max_regions=5,
        )
        ok = (
            matching == 2
            and regions == 2
            and evaluated == 4
            and len(candidates) == 2
            and candidates[0]["bbox"] == [10.0, 20.0, 11.0, 21.0]
            and candidates[0]["cell_count"] == 1
        )
        return ok, f"matching={matching} regions={regions}"

    def observations() -> tuple[bool, str]:
        parsed = _parse_observation(
            "height=10;shadow=5;datetime=2024-06-01T14:00:00+02:00"
        )
        ok = parsed is not None and parsed[0]["datetime_utc"] == "2024-06-01T12:00:00Z"
        ok = ok and _parse_observation(
            "height=0;shadow=5;datetime=2024-06-01T12:00:00Z"
        ) is None
        return ok, "UTC normalization and rejection checks"

    check("pin_file", _pin_file_matches)
    check("package_import", lambda: (bool(_package_version()), _package_version()))
    check("grid_file", lambda: (os.path.isfile(GRID_PATH), GRID_PATH))
    check(
        "grid_metadata",
        lambda: (
            json.loads(Path(GRID_PATH).read_text(encoding="utf-8")).get("angular_resolution")
            == 0.5,
            "angular_resolution=0.5",
        ),
    )
    check("offline_imports", lambda: (not _network_imports(), "no outbound-client imports"))
    check("observation_parsing", observations)
    check("candidate_binning", binning)
    check("computation", computation)
    def observation_arguments() -> tuple[bool, str]:
        good = _parse_args(
            ["--observation", "height=10;shadow=5;datetime=2024-06-01T12:00:00Z"]
        )
        bad = _parse_args(["--observation", "bad"])
        ok = (
            good is not None
            and _parse_observation(good["observation"]) is not None
            and bad is not None
            and _parse_observation(bad["observation"]) is None
        )
        return ok, "syntax accepted; semantics enforced by the driver"

    check("observation_validation", observation_arguments)
    ok = all(item["ok"] for item in checks)
    print(json.dumps({"shadowfinder_selftest": "ok" if ok else "fail", "checks": checks}, indent=2))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--health" in arguments:
        return _health()
    if "--selftest" in arguments:
        return _selftest()
    options = _parse_args(arguments)
    if options is None:
        print(
            json.dumps(
                {"source": "shadowfinder", "status": "invalid_target", "error": OBSERVATION_HELP}
            )
        )
        return 2
    parsed = _parse_observation(options["observation"])
    if parsed is None:
        print(
            json.dumps(
                {"source": "shadowfinder", "status": "invalid_target", "error": OBSERVATION_HELP}
            )
        )
        return 2
    public, when = parsed
    try:
        payload = _run(public, when, {**options, "grid_path": GRID_PATH})
    except Exception as exc:  # pragma: no cover - image only
        print(
            json.dumps(
                {
                    "source": "shadowfinder",
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
