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


def _prov(adapter: AdapterDescriptor, source_url: str | None, confidence: float, raw: bytes,
          notes: list[str] | None = None) -> Provenance:
    return Provenance(
        tool=adapter.name,
        source_url=source_url,
        observed_at=datetime.now(timezone.utc),
        confidence=confidence,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=notes or [],
    )


def _result(request: AdapterRunRequest, adapter: AdapterDescriptor, started: datetime,
            findings: list[Finding], stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
    return AdapterRunResult(
        run_id=request.run_id,
        adapter=adapter,
        status="succeeded" if exit_code == 0 else "partial",
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        exit_code=exit_code,
        findings=findings,
        stderr_tail=stderr[-4000:],
        stdout_tail=stdout[-4000:],
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


class ShadowFinderAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="shadowfinder", license="MIT",
        input_types=[SeedType.SHADOW_OBSERVATION], output_types=[EntityType.GEO_EVIDENCE],
        legal_notes=[
            "Offline solar-geometry analysis of a user-supplied observation — object height, shadow length and a UTC datetime. The pinned ShadowFinder package runs locally; no coordinate, measurement or query is transmitted.",
            "Outputs are coarse possibility regions on a 0.5-degree solar grid, summarised into 1-degree bins. They are not a confirmed location, not a probability, and require independent corroboration.",
            "MIT-licensed upstream, operated unmodified in its own image; see docker/shadowfinder/RATE_LIMITS.md.",
        ],
        rate_limit="One observation per invocation; pure local computation (no requests, retries or cache); the full 208,800-cell grid is evaluated in memory.",
        invocation="Docker / CLI", version_pin="0.7.1 (commit 215485abd5a46a9b98c4ba0fbfce7df6b6bb1be8)",
        upstream="https://github.com/bellingcat/ShadowFinder", network_required=False,
        docker_image="aletheia/shadowfinder:v1",
        output_schema={"status": "string", "observation": "object", "grid": "object", "candidates": "array"},
        health_check="--health", requires_authorization_assertion=False,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.SHADOW_OBSERVATION

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["--observation", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc); raw = stdout.encode(); findings = []
        try: payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: payload = {}
        if not isinstance(payload, dict):
            payload = {}
        target = request.seed.value
        status = payload.get("status") if isinstance(payload.get("status"), str) else "unknown"
        observation = payload.get("observation") if isinstance(payload.get("observation"), dict) else {}
        grid = payload.get("grid") if isinstance(payload.get("grid"), dict) else {}
        thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
        regions_total = payload.get("regions_total")
        if isinstance(regions_total, bool) or not isinstance(regions_total, int):
            regions_total = None
        run_attributes = {
            "source": self.descriptor.name,
            "status": status,
            "target": target,
            "observation": observation,
            "grid": grid,
            "thresholds": thresholds,
            "truncated": payload.get("truncated") is True,
        }
        if regions_total is not None:
            run_attributes["regions_total"] = regions_total
        reason = payload.get("error") if isinstance(payload.get("error"), str) else ""
        if reason:
            run_attributes["reason"] = reason
        findings.append(Finding(
            entity_type=EntityType.GEO_EVIDENCE, value=f"{self.descriptor.name}:run:{status}",
            attributes=run_attributes,
            provenance=_prov(self.descriptor, self.descriptor.upstream, 0.3, raw,
                             notes=["Offline shadow observation processed by the pinned ShadowFinder package; nothing was fabricated or transmitted."]),
        ))
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        for index, candidate in enumerate(candidates[:50]):
            if not isinstance(candidate, dict):
                continue
            position = index + 1
            rank = candidate.get("rank")
            if isinstance(rank, bool) or not isinstance(rank, int):
                rank = position
            bbox = _pair(candidate.get("bbox"), 4)
            centroid = _pair(candidate.get("centroid"), 2)
            attributes = {"source": self.descriptor.name, "target": target, "rank": rank}
            if bbox is not None:
                attributes["bbox"] = bbox
            if centroid is not None:
                attributes["centroid"] = centroid
            best_cell = candidate.get("best_cell")
            if isinstance(best_cell, dict):
                lat = _number(best_cell.get("lat"))
                lon = _number(best_cell.get("lon"))
                difference = _number(best_cell.get("relative_difference"))
                if lat is not None and lon is not None and difference is not None:
                    attributes["best_cell"] = {"lat": lat, "lon": lon, "relative_difference": difference}
            count = candidate.get("cell_count")
            if isinstance(count, int) and not isinstance(count, bool):
                attributes["cell_count"] = count
            tolerance = _number(thresholds.get("tolerance"))
            if tolerance is not None:
                attributes["tolerance"] = tolerance
            findings.append(Finding(
                entity_type=EntityType.GEO_EVIDENCE, value=f"{self.descriptor.name}:candidate:{position}",
                attributes=attributes,
                provenance=_prov(self.descriptor, self.descriptor.upstream, 0.4, raw,
                                 notes=["Coarse possibility region from solar geometry; not a confirmed location."]),
            ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)
