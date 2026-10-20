"""Open-Meteo weather observation adapter.

One coordinate, optionally with a date, is sent to Open-Meteo's keyless free
API. The free tier is non-commercial and requires CC-BY 4.0 attribution; every
finding carries the attribution string. Weather is environmental context, not
proof of an image's location or time.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor,
    AdapterRunRequest,
    AdapterRunResult,
    EntityType,
    Finding,
    Provenance,
    SeedType,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _prov(adapter: AdapterDescriptor, raw: bytes) -> Provenance:
    return Provenance(
        tool=adapter.name,
        source_url=adapter.upstream,
        observed_at=datetime.now(timezone.utc),
        confidence=0.8,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=[
            "Open-Meteo free API; non-commercial use and CC-BY 4.0 attribution. "
            "Environmental context only, not proof of image location or time."
        ],
    )


def _target(value: str) -> tuple[float, float, str | None]:
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
    day = parts[2] if len(parts) == 3 else None
    if day is not None:
        if not DATE_RE.fullmatch(day):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError("date must be a real calendar date") from exc
    return latitude, longitude, day


class WeatherAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="weather",
        license="CC-BY 4.0 (Open-Meteo data; attribution required)",
        input_types=[SeedType.GEOLOCATION],
        output_types=[EntityType.GEO_EVIDENCE],
        legal_notes=[
            "Open-Meteo's free API is keyless but limited to non-commercial use, "
            "with published limits of 600 calls/minute, 5,000/hour and 10,000/day. "
            "Aletheia's use is free/open-source and non-commercial; downstream "
            "commercial use must use Open-Meteo's paid API. Every finding carries "
            "the required 'Weather data by Open-Meteo.com (CC-BY 4.0)' attribution.",
            "One coordinate is sent per run; no identity, account, or personal data "
            "is sent. Weather at a coordinate is environmental context for image or "
            "place corroboration, not proof that an image was taken there or then.",
            "No live target is on file; verification is fixture-based. See "
            "docker/weather/RATE_LIMITS.md.",
        ],
        rate_limit=(
            "One Open-Meteo request per run; no retries, pagination, or caching. "
            "The free tier is documented at 600 calls/minute, 5,000/hour and "
            "10,000/day per IP/application. See docker/weather/RATE_LIMITS.md"
        ),
        invocation="Docker / CLI",
        version_pin="1.0 (Open-Meteo API reviewed 2026-10-20)",
        upstream="https://open-meteo.com/",
        network_required=True,
        docker_image="aletheia/weather:v1",
        output_schema={"finding_type": "Finding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.GEOLOCATION

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        latitude, longitude, day = _target(request.seed.value.strip())
        normalized = f"{latitude:g},{longitude:g}"
        if day:
            normalized += f",{day}"
        return [normalized]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str,
              stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode("utf-8", "replace")
        findings: list[Finding] = []
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        status = _text(payload.get("status"), 32) or ("ok" if exit_code == 0 else "error")
        mode = _text(payload.get("mode"), 32)
        query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
        grid = payload.get("grid") if isinstance(payload.get("grid"), dict) else {}
        observation = payload.get("observation") if isinstance(payload.get("observation"), dict) else {}
        errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
        if status in {"ok", "partial"} and not observation:
            status = "partial"
            errors = [*errors, "response contained no weather observation"]
        findings.append(Finding(
            entity_type=EntityType.GEO_EVIDENCE,
            value=f"{self.descriptor.name}:run:{status}",
            attributes={
                "source": self.descriptor.name,
                "status": status,
                "mode": mode,
                "query": {
                    "latitude": _number(query.get("latitude")),
                    "longitude": _number(query.get("longitude")),
                    "date": _text(query.get("date"), 32),
                },
                "grid": {
                    "latitude": _number(grid.get("latitude")),
                    "longitude": _number(grid.get("longitude")),
                    "elevation": _number(grid.get("elevation")),
                    "timezone": _text(grid.get("timezone"), 64),
                },
                "observation_fields": sorted(observation.keys())[:64],
                "errors": [_text(item, 300) for item in errors[:5] if _text(item, 300)],
                "attribution": _text(payload.get("attribution"), 200),
            },
            provenance=_prov(self.descriptor, raw),
        ))
        if status in {"ok", "partial"} and observation:
            day = _text(query.get("date"), 32)
            value = (
                f"{self.descriptor.name}:observation:"
                f"{query.get('latitude')},{query.get('longitude')}"
            )
            if day:
                value += f":{day}"
            findings.append(Finding(
                entity_type=EntityType.GEO_EVIDENCE,
                value=value,
                attributes={
                    "source": self.descriptor.name,
                    "mode": mode,
                    "query": {
                        "latitude": _number(query.get("latitude")),
                        "longitude": _number(query.get("longitude")),
                        "date": day,
                    },
                    "grid": grid,
                    "units": payload.get("units") if isinstance(payload.get("units"), dict) else {},
                    "observation": observation,
                    "attribution": _text(payload.get("attribution"), 200),
                },
                provenance=_prov(self.descriptor, raw),
            ))
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded" if exit_code == 0 and status == "ok" else "partial",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )
