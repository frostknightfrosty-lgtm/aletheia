from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor, AdapterRunRequest, AdapterRunResult, EntityType, Finding,
    Provenance, SeedType,
)

MAX_INPUT_BYTES = 1_000_000


def _prov(adapter: AdapterDescriptor, confidence: float, raw: bytes,
          notes: list[str] | None = None) -> Provenance:
    return Provenance(
        tool=adapter.name,
        source_url=adapter.upstream,
        observed_at=datetime.now(timezone.utc),
        confidence=confidence,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=notes or [],
    )


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _pair(value, size: int) -> list[float] | None:
    if not isinstance(value, list) or len(value) != size:
        return None
    numbers = [_number(item) for item in value]
    if any(item is None for item in numbers):
        return None
    return numbers


class PybdshadowAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="pybdshadow", license="BSD-3-Clause",
        input_types=[SeedType.FILE_PATH], output_types=[EntityType.GEO_EVIDENCE],
        legal_notes=[
            "Offline building-shadow geometry from a user-supplied local JSON document (footprints, heights and one UTC datetime). The pinned pybdshadow package runs locally; no coordinate or query is transmitted.",
            "Outputs are geometric shadow summaries (bbox, centroid, geodesic area, polygon/vertex counts), not a confirmed location, not a probability, and require independent corroboration.",
            "BSD-3-Clause upstream, operated unmodified in its own image; the package's optional footprint-fetching helpers are never invoked. See docker/pybdshadow/RATE_LIMITS.md.",
        ],
        rate_limit="One local JSON input per invocation; at most 200 buildings and 1,000 vertices per building; pure local geometry (no requests, retries or cache).",
        invocation="Docker / CLI", version_pin="0.3.5 (commit e2665ee7a6527b9fb0d581bbf7d6dc2914015b02)",
        upstream="https://github.com/ni1o1/pybdshadow", network_required=False,
        docker_image="aletheia/pybdshadow:v1",
        output_schema={"status": "string", "input": "object", "shadows": "array"},
        health_check="--health", requires_authorization_assertion=False,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.FILE_PATH

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        source = Path(request.seed.value)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"local building-shadow input not found: {source}")
        data = source.read_bytes()
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError(f"building-shadow input exceeds {MAX_INPUT_BYTES} bytes")
        destination = workspace / "input.json"
        destination.write_bytes(data)
        return ["/work/input.json"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode()
        findings: list[Finding] = []
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        target = request.seed.value
        status = payload.get("status") if isinstance(payload.get("status"), str) else "unknown"
        input_info = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
        shadows_total = payload.get("shadows_total")
        if isinstance(shadows_total, bool) or not isinstance(shadows_total, int):
            shadows_total = None
        run_attributes = {
            "source": self.descriptor.name,
            "status": status,
            "target": target,
            "input": input_info,
            "thresholds": thresholds,
        }
        if shadows_total is not None:
            run_attributes["shadows_total"] = shadows_total
        reason = payload.get("error") if isinstance(payload.get("error"), str) else ""
        if reason:
            run_attributes["reason"] = reason
        findings.append(Finding(
            entity_type=EntityType.GEO_EVIDENCE, value=f"{self.descriptor.name}:run:{status}",
            attributes=run_attributes,
            provenance=_prov(self.descriptor, 0.3, raw,
                             notes=["Offline building-shadow geometry computed by the pinned pybdshadow package; nothing was fabricated or transmitted."]),
        ))
        shadows = payload.get("shadows") if isinstance(payload.get("shadows"), list) else []
        for index, shadow in enumerate(shadows[:200]):
            if not isinstance(shadow, dict):
                continue
            position = index + 1
            attributes = {"source": self.descriptor.name, "target": target, "rank": position}
            building_id = shadow.get("building_id")
            if isinstance(building_id, str) and building_id:
                attributes["building_id"] = building_id
            bbox = _pair(shadow.get("bbox"), 4)
            centroid = _pair(shadow.get("centroid"), 2)
            if bbox is None or centroid is None:
                continue
            attributes["bbox"] = bbox
            attributes["centroid"] = centroid
            area = _number(shadow.get("shadow_area_m2"))
            if area is not None:
                attributes["shadow_area_m2"] = area
            polygons = shadow.get("polygons")
            if isinstance(polygons, int) and not isinstance(polygons, bool):
                attributes["polygons"] = polygons
            vertices = shadow.get("vertices")
            if isinstance(vertices, int) and not isinstance(vertices, bool):
                attributes["vertices"] = vertices
            findings.append(Finding(
                entity_type=EntityType.GEO_EVIDENCE, value=f"{self.descriptor.name}:shadow:{position}",
                attributes=attributes,
                provenance=_prov(self.descriptor, 0.4, raw,
                                 notes=["Building-shadow geometry from a local footprint and datetime; not a confirmed location."]),
            ))
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded" if exit_code == 0 else "partial",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )
