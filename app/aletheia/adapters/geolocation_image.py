from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
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


# The runner implements only sub-sources whose request contract or local entry
# point was verified from their own documentation. The complete source review,
# including the auditable non-querying reasons for the other candidates, is in
# docker/geolocation_image/RATE_LIMITS.md.
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


class GeoEvidenceFinding(Finding):
    """A normalized geolocation or image-forensics observation."""

    subject: str | None = None
    record_type: str | None = None
    location: dict[str, Any] | None = None
    observation_time: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        location: dict[str, Any] | None = None,
        observation_time: str | None = None,
        details: dict[str, Any] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        provenance: Provenance | None = None,
    ) -> None:
        attributes: dict[str, Any] = {"source": source}
        if record_type:
            attributes["record_type"] = record_type
        if location:
            attributes["location"] = location
        if observation_time:
            attributes["observation_time"] = observation_time
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence
        if provenance is None:
            raw = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="geolocation_image",
                source_url=source_url or _SOURCE_CITATIONS.get(source),
                confidence=0.80,
                raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )
        super().__init__(
            entity_type=EntityType.GEO_EVIDENCE,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        self.subject = subject
        self.record_type = record_type
        self.location = location
        self.observation_time = observation_time


_SOURCE_CITATIONS = {
    "mapillary": "https://mapillary.github.io/mapillary-python-sdk/docs/mapillary.models/mapillary.models.client/",
    "nominatim": "https://nominatim.org/release-docs/latest/api/Search/",
    "copernicus-stac": "https://documentation.dataspace.copernicus.eu/APIs/STAC.html",
    "dfit": "https://pypi.org/project/dfit-toolkit/1.0.0/",
    "steg-analyzer": "https://pypi.org/project/steg-analyzer/",
    "pic-image-search": "https://github.com/kitUIN/PicImageSearch",
    "tracelines": "https://pypi.org/project/tracelines/0.2.0/",
    "shadowfinder": "https://github.com/bellingcat/ShadowFinder",
    "pybdshadow": "https://pybdshadow.readthedocs.io/en/stable/",
    "youtube-geofind": "https://developers.google.com/youtube/v3/docs/search/list",
    "geolocator": "https://github.com/Developer-Mike/geolocator",
    "betaface": "https://www.betaface.com/products.html",
}


def _provenance(
    source: str,
    raw_evidence: dict[str, Any],
    notes: list[str],
    *,
    source_url: str | None = None,
) -> Provenance:
    return Provenance(
        tool="geolocation_image",
        source_url=source_url or _SOURCE_CITATIONS.get(source),
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(
            json.dumps(raw_evidence, sort_keys=True).encode()
        ).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_record(data: dict[str, Any]) -> dict[str, Any] | None:
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None


_RECORD_TYPES = {
    "mapillary": "street_level_image_observation",
    "nominatim": "geocoder_place_observation",
    "copernicus-stac": "satellite_catalogue_item",
    "dfit": "image_forensics_metadata",
    "steg-analyzer": "image_steganography_analysis",
}


def _extract_subject(data: dict[str, Any], source: str) -> str:
    record = _first_record(data)
    if record is None:
        return source
    record_id = record.get("record_id")
    return f"{source.upper()}:{record_id}" if record_id else source


def _extract_location(data: dict[str, Any]) -> dict[str, Any] | None:
    record = _first_record(data)
    if record is None:
        return None
    location = record.get("location")
    return location if isinstance(location, dict) else None


def _extract_time(data: dict[str, Any]) -> str | None:
    record = _first_record(data)
    if record is None:
        return None
    value = record.get("observation_time")
    return value if isinstance(value, str) and value.strip() else None


def _extract_details(data: dict[str, Any]) -> dict[str, Any] | None:
    record = _first_record(data)
    if record is None:
        return None
    details = {
        "api_source": data.get("api_source"),
        "api_documentation": data.get("api_documentation"),
        "endpoint": data.get("endpoint"),
        "module": data.get("module"),
        "invocation": data.get("invocation"),
        "query": data.get("query"),
        "record_count": data.get("record_count"),
        "truncated": data.get("truncated", False),
        "record_id": record.get("record_id"),
        "detail": record.get("detail"),
        "source_fields": record.get("source_fields"),
    }
    return {key: value for key, value in details.items() if value is not None}


def _stage_image(request: AdapterRunRequest, workspace: Path) -> str:
    source = Path(request.seed.value).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"image evidence file not found: {source}")
    suffix = source.suffix.lower() or ".bin"
    workspace.mkdir(parents=True, exist_ok=True)
    staged_name = "geolocation-image-input" + suffix
    shutil.copy2(source, workspace / staged_name)
    # run_docker mounts workspace at /work. Passing a host path would fail inside
    # the container, so the command intentionally uses the container path.
    return "/work/" + staged_name


class GeolocationImageAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="geolocation_image",
        license=(
            "Composite adapter: Mapillary Graph API; OpenStreetMap Nominatim; Copernicus Data "
            "Space Ecosystem STAC catalogue; MIT-licensed dfit-toolkit; and MIT-licensed "
            "steg-analyzer."
        ),
        input_types=[SeedType.GEOLOCATION, SeedType.NAME, SeedType.IMAGE, SeedType.FILE_PATH],
        output_types=[EntityType.GEO_EVIDENCE],
        legal_notes=[
            "The implemented HTTP paths are one bounded request each to Mapillary, Nominatim and the Copernicus STAC catalogue. Mapillary is skipped without its free client token. Copernicus catalogue search requires a geolocation seed with an ISO-8601 datetime interval; product download is never performed.",
            "The two local image paths are narrow read-only analysis calls: dfit metadata and steg-analyzer metadata/ELA/histogram analysis. This adapter never invokes extraction, password, cracking, account, login, or credential-related commands. It stores a summary and output hash rather than arbitrary extracted strings.",
            "Seven candidates are documented skips in docker/geolocation_image/RATE_LIMITS.md. They are reported once per run with their exact reason and never contacted. This includes youtube-geofind because its YouTube Data API vendor source already belongs to the existing youtube-api adapter.",
            "A geolocation or imagery record is an observation from a source, not evidence of a person's identity, ownership, or presence. Review its provider metadata and any temporal limitations before relying on it.",
        ],
        rate_limit=(
            "At most one request per implemented HTTP sub-source per run and no pagination; Nominatim's "
            "public policy permits at most one request per second. Mapillary and Copernicus publish no "
            "numeric limit in the verified documentation. Local image paths run once each. See "
            "docker/geolocation_image/RATE_LIMITS.md."
        ),
        invocation="HTTPS catalogue/geocoding APIs and two local image-analysis CLIs via a dedicated Docker runner (aletheia/geolocation-image:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/geolocation_image",
        network_required=True,
        docker_image="aletheia/geolocation-image:v1",
        output_schema={"finding_type": "GeoEvidenceFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=["MAPILLARY_ACCESS_TOKEN"],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in set(self.descriptor.input_types)

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        if request.seed.type == SeedType.GEOLOCATION:
            return ["geolocation", request.seed.value]
        if request.seed.type == SeedType.NAME:
            return ["name", request.seed.value]
        if request.seed.type in {SeedType.IMAGE, SeedType.FILE_PATH}:
            return ["image", _stage_image(request, workspace)]
        raise ValueError(f"Unsupported seed type for geolocation_image: {request.seed.type}")

    def parse(
        self,
        request: AdapterRunRequest,
        workspace: Path,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        if exit_code != 0:
            return AdapterRunResult(
                run_id=request.run_id,
                adapter=self.descriptor,
                status="failed",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=exit_code,
                findings=[],
                stderr_tail=stderr[-4000:],
                stdout_tail=stdout[-4000:],
            )
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return AdapterRunResult(
                run_id=request.run_id,
                adapter=self.descriptor,
                status="partial",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=1,
                findings=[],
                stderr_tail="Runner output was not valid JSON",
                stdout_tail=stdout[-4000:],
            )

        findings: list[Finding] = []
        for source_result in payload.get("sources", []):
            if not isinstance(source_result, dict):
                continue
            source = str(source_result.get("source", "unknown"))
            skipped = bool(source_result.get("skipped"))
            reason = source_result.get("skip_reason")
            error = source_result.get("error")
            status = source_result.get("http_status", 0)
            data = source_result.get("data")
            if skipped:
                raw = {"skipped": True, "reason": reason}
                findings.append(
                    GeoEvidenceFinding(
                        subject=f"{source}:skipped",
                        source=source,
                        details=raw,
                        raw_evidence=raw,
                        provenance=_provenance(
                            source,
                            raw,
                            [f"Skipped: {reason}"],
                            source_url=_SOURCE_CITATIONS.get(source),
                        ),
                    )
                )
                continue
            if error:
                raw = {"error": error, "http_status": status}
                findings.append(
                    GeoEvidenceFinding(
                        subject=f"{source}:error",
                        source=source,
                        details=raw,
                        raw_evidence=raw,
                        provenance=_provenance(
                            source,
                            raw,
                            [f"Error: {error}"],
                            source_url=(data.get("endpoint") if isinstance(data, dict) else None)
                            or _SOURCE_CITATIONS.get(source),
                        ),
                    )
                )
                continue
            if not isinstance(data, dict) or _first_record(data) is None:
                continue
            findings.append(
                GeoEvidenceFinding(
                    subject=_extract_subject(data, source),
                    source=source,
                    record_type=_RECORD_TYPES.get(source),
                    location=_extract_location(data),
                    observation_time=_extract_time(data),
                    details=_extract_details(data),
                    raw_evidence=data,
                    provenance=_provenance(
                        source,
                        data,
                        [f"Normalized from {source}"],
                        source_url=data.get("endpoint") or _SOURCE_CITATIONS.get(source),
                    ),
                )
            )
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )
