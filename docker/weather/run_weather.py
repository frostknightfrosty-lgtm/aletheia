"""Bounded Open-Meteo weather observation driver.

One coordinate (and optional past/future date) in, one normalized JSON
document out. Open-Meteo's free API is keyless but non-commercial, limited to
600 calls/minute, 5,000/hour and 10,000/day per IP/application, and its data is
CC-BY 4.0. The runner makes one API call per invocation, never retries, and
emits the attribution string with every document.

* ``lat,lon`` queries the forecast endpoint's current conditions.
* ``lat,lon,YYYY-MM-DD`` queries the historical archive for a past date, or the
  forecast daily endpoint for today/future dates.

Weather at a coordinate is environmental context for image/place corroboration,
not proof that an image was taken there or then.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REVIEWED_ON = "2026-10-20"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
NETWORK_HOSTS = (FORECAST_API, ARCHIVE_API)
USER_AGENT = (
    "Aletheia/0.1 (https://github.com/frostknightfrosty-lgtm/aletheia; "
    "public weather lookup)"
)
ATTRIBUTION = "Weather data by Open-Meteo.com (CC-BY 4.0)"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30
MAX_ERRORS = 5
MAX_DAILY_DAYS = 31
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CURRENT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
)
DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "weather_code",
    "sunrise",
    "sunset",
)


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _parse_target(value: str) -> dict[str, Any]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) not in {2, 3}:
        raise ValueError("target must be latitude,longitude[,YYYY-MM-DD]")
    try:
        latitude = float(parts[0])
        longitude = float(parts[1])
    except ValueError as exc:
        raise ValueError("latitude and longitude must be numbers") from exc
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be between -180 and 180")
    day: str | None = None
    if len(parts) == 3:
        day = parts[2]
        if not DATE_RE.fullmatch(day):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError("date must be a real calendar date") from exc
    return {"value": value, "latitude": latitude, "longitude": longitude, "date": day}


def _target_for(value: str) -> dict[str, Any]:
    target = _parse_target(value)
    if target["date"] and target["date"] < datetime.now(timezone.utc).date().isoformat():
        target["mode"] = "archive"
    elif target["date"]:
        target["mode"] = "forecast_daily"
    else:
        target["mode"] = "forecast_current"
    return target


def _fetch_json(url: str) -> tuple[Any, int, str | None]:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
            if len(body) > MAX_RESPONSE_BYTES:
                return None, status, "response exceeded the 4 MB safety limit"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, f"HTTP {exc.code}: {detail[:300]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, f"{type(exc).__name__}: {exc}"
    try:
        return json.loads(body.decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, f"JSON decode error: {exc}"


def _url_for(target: dict[str, Any]) -> str:
    mode = target["mode"]
    if mode == "archive":
        params = {
            "latitude": str(target["latitude"]),
            "longitude": str(target["longitude"]),
            "start_date": target["date"],
            "end_date": target["date"],
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "UTC",
        }
        return f"{ARCHIVE_API}?{urllib.parse.urlencode(params)}"
    if mode == "forecast_daily":
        params = {
            "latitude": str(target["latitude"]),
            "longitude": str(target["longitude"]),
            "start_date": target["date"],
            "end_date": target["date"],
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "UTC",
        }
        return f"{FORECAST_API}?{urllib.parse.urlencode(params)}"
    params = {
        "latitude": str(target["latitude"]),
        "longitude": str(target["longitude"]),
        "current": ",".join(CURRENT_FIELDS),
        "timezone": "UTC",
    }
    return f"{FORECAST_API}?{urllib.parse.urlencode(params)}"


def _clean_units(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, unit in value.items():
        if isinstance(key, str) and isinstance(unit, str) and unit.strip():
            out[key[:64]] = unit[:32]
    return out


def _clean_current(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, str):
            out[key[:64]] = item[:64]
        elif (number := _number(item)) is not None:
            out[key[:64]] = number
    return out


def _clean_daily(value: Any) -> dict[str, list[Any]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[Any]] = {}
    for key, items in value.items():
        if not isinstance(key, str) or not isinstance(items, list):
            continue
        clean: list[Any] = []
        for item in items[:MAX_DAILY_DAYS]:
            if isinstance(item, str):
                clean.append(item[:64])
            elif (number := _number(item)) is not None:
                clean.append(number)
        if clean:
            out[key[:64]] = clean
    return out


def _normalise(raw: Any, target: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Open-Meteo response must be a JSON object")
    if "error" in raw and raw.get("error") is True:
        raise ValueError(f"Open-Meteo error: {_text(raw.get('reason'), 300) or 'unknown'}")
    current = _clean_current(raw.get("current"))
    daily = _clean_daily(raw.get("daily"))
    if not current and not daily:
        raise ValueError("response contains neither current nor daily observations")
    mode = "archive" if daily and not current else "forecast_current"
    if target is not None:
        mode = target["mode"]
    units = _clean_units(raw.get("current_units") if current else raw.get("daily_units"))
    if current:
        observation: dict[str, Any] = current
        day = _text(current.get("time"), 32)
        if day and "T" in day:
            day = day.split("T", 1)[0]
    else:
        observation = daily
        day = (daily.get("time") or [None])[0]
    latitude = _number(raw.get("latitude"))
    longitude = _number(raw.get("longitude"))
    if target is not None:
        latitude = target["latitude"]
        longitude = target["longitude"]
        day = target["date"] or day
    if latitude is None or longitude is None:
        raise ValueError("response is missing latitude/longitude")
    errors: list[str] = []
    if day and not DATE_RE.fullmatch(str(day)):
        errors.append("observation time is not YYYY-MM-DD")
        day = None
    return {
        "source": "weather",
        "status": "partial" if errors else "ok",
        "mode": mode,
        "query": {
            "latitude": latitude,
            "longitude": longitude,
            "date": day,
        },
        "grid": {
            "latitude": _number(raw.get("latitude")),
            "longitude": _number(raw.get("longitude")),
            "elevation": _number(raw.get("elevation")),
            "timezone": _text(raw.get("timezone"), 64),
            "utc_offset_seconds": _number(raw.get("utc_offset_seconds")),
        },
        "units": units,
        "observation": observation,
        "attribution": ATTRIBUTION,
        "errors": errors,
    }


_SAMPLE_FORECAST = {
    "latitude": 51.49349,
    "longitude": -0.13172913,
    "generationtime_ms": 0.4,
    "utc_offset_seconds": 0,
    "timezone": "GMT",
    "timezone_abbreviation": "GMT",
    "elevation": 8.0,
    "current_units": {"time": "iso8601", "temperature_2m": "°C",
                      "precipitation": "mm", "weather_code": "wmo code"},
    "current": {"time": "2026-10-20T19:30", "interval": 900,
                "temperature_2m": 12.0, "precipitation": 0.0,
                "weather_code": 3, "wind_speed_10m": 10.8},
}
_SAMPLE_ARCHIVE = {
    "latitude": 51.493847,
    "longitude": -0.1630249,
    "elevation": 8.0,
    "utc_offset_seconds": 0,
    "timezone": "GMT",
    "daily_units": {"time": "iso8601", "temperature_2m_max": "°C",
                    "temperature_2m_min": "°C", "precipitation_sum": "mm"},
    "daily": {"time": ["2024-06-01"], "temperature_2m_max": [16.5],
              "temperature_2m_min": [8.8], "precipitation_sum": [0.0],
              "weather_code": [3]},
}


def _health() -> int:
    payload = {
        "source": "weather",
        "reviewed_on": REVIEWED_ON,
        "endpoints": list(NETWORK_HOSTS),
        "network_required": True,
        "credentials_required": False,
        "free_tier": "non-commercial; 600/min, 5000/hour, 10000/day",
        "attribution": ATTRIBUTION,
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    print("ok")
    return 0


def _selftest() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        target = _parse_target("51.5007,-0.1246,2024-06-01")
        check("target_parse", target["latitude"] == 51.5007
              and target["longitude"] == -0.1246 and target["date"] == "2024-06-01",
              "latitude,longitude,date")
    except Exception as exc:  # noqa: BLE001
        check("target_parse", False, str(exc)[:200])
    for bad in ("51.5", "91,-0.1", "51.5,-181", "51.5,-0.1,2024-13-01"):
        try:
            _parse_target(bad)
            check(f"reject_{bad}", False, "accepted invalid target")
        except ValueError:
            check(f"reject_{bad}", True, "rejected")
    try:
        forecast = _normalise(_SAMPLE_FORECAST)
        check("forecast_normalisation", forecast["mode"] == "forecast_current"
              and forecast["query"]["date"] == "2026-10-20"
              and forecast["observation"]["temperature_2m"] == 12.0
              and forecast["attribution"] == ATTRIBUTION,
              "synthetic forecast")
    except Exception as exc:  # noqa: BLE001
        check("forecast_normalisation", False, str(exc)[:200])
    try:
        archive = _normalise(_SAMPLE_ARCHIVE)
        check("archive_normalisation", archive["mode"] == "archive"
              and archive["query"]["date"] == "2024-06-01"
              and archive["observation"]["temperature_2m_max"] == [16.5],
              "synthetic archive")
    except Exception as exc:  # noqa: BLE001
        check("archive_normalisation", False, str(exc)[:200])
    check("network_hosts", all(host.startswith("https://") for host in NETWORK_HOSTS),
          ", ".join(NETWORK_HOSTS))
    check("bounds", MAX_DAILY_DAYS == 31 and MAX_RESPONSE_BYTES == 4 * 1024 * 1024,
          f"daily_days={MAX_DAILY_DAYS}")
    print(json.dumps({
        "weather_selftest": "ok" if all(c["ok"] for c in checks) else "failed",
        "reviewed_on": REVIEWED_ON,
        "checks": checks,
    }, sort_keys=True, indent=2))
    return 0 if all(item["ok"] for item in checks) else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--health", action="store_true")
    group.add_argument("--selftest", action="store_true")
    group.add_argument("--normalize", metavar="RESPONSE_JSON")
    parser.add_argument("target", nargs="?")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.health:
        return _health()
    if args.selftest:
        return _selftest()
    if args.normalize:
        try:
            raw = json.loads(Path(args.normalize).read_text(encoding="utf-8"))
            print(json.dumps(_normalise(raw), sort_keys=True, indent=2))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"source": "weather", "status": "invalid_response",
                              "error": str(exc)[:300]}, sort_keys=True))
            return 2
    if not args.target:
        print(json.dumps({"source": "weather", "status": "invalid_target",
                          "error": "latitude,longitude[,YYYY-MM-DD] is required"},
                         sort_keys=True))
        return 2
    try:
        target = _target_for(args.target)
    except ValueError as exc:
        print(json.dumps({"source": "weather", "status": "invalid_target",
                          "error": str(exc)}, sort_keys=True))
        return 2
    raw, status, error = _fetch_json(_url_for(target))
    if error:
        print(json.dumps({"source": "weather", "status": "error",
                          "http_status": status, "error": error}, sort_keys=True))
        return 1
    try:
        print(json.dumps(_normalise(raw, target), sort_keys=True, indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"source": "weather", "status": "error",
                          "error": str(exc)[:300]}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
