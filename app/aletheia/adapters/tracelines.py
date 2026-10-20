from __future__ import annotations

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
    import hashlib
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


class TracelinesAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="tracelines", license="AGPL-3.0-or-later",
        input_types=[SeedType.GEOLOCATION], output_types=[EntityType.UNKNOWN],
        legal_notes=[
            "Runs only the pinned package's documented providers — Mapillary (free MAPILLARY_TOKEN; recorded skip without it) and keyless KartaView — over a small bbox derived from one point seed (max 300 m radius); no retries and no disk cache. The Google provider (undocumented internal streetlevel endpoints) is excluded structurally: streetlevel is never installed and the driver refuses to run if it is present; see docker/tracelines/RATE_LIMITS.md.",
            "Coverage data is summarized in memory (segment length, point count, centroid, endpoints) with Mapillary/KartaView CC-BY-SA 4.0 attribution; no coverage geometry is written or redistributed.",
            "Explicit authorization is required for the queried point: it (and the derived bbox) is transmitted to Mapillary and KartaView.",
        ],
        rate_limit="One point per invocation (<=300 m radius): 1-4 Mapillary z14 tile requests and at most two KartaView sequence requests; no pagination, no retries, no cache.",
        invocation="Docker / CLI", version_pin="0.2.0 (commit 99257f0519b30ce7d890db25252f6cf440fa102e)",
        upstream="https://github.com/Prekzursil/tracelines", network_required=True,
        docker_image="aletheia/tracelines:v1",
        output_schema={"sources": "object", "status": "string", "bbox": "number[]"},
        health_check="--health", requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.GEOLOCATION

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["--point", request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc); raw = stdout.encode(); findings = []
        try: payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError: payload = {}
        if not isinstance(payload, dict):
            payload = {}
        target = request.seed.value
        bbox = payload.get("bbox") if isinstance(payload.get("bbox"), list) else None
        sources = payload.get("sources") if isinstance(payload.get("sources"), dict) else {}
        for source_name in sorted(sources):
            entry = sources[source_name] if isinstance(sources[source_name], dict) else {}
            status = entry.get("status") if isinstance(entry.get("status"), str) else "error"
            reason = entry.get("reason") if isinstance(entry.get("reason"), str) else ""
            attributes = {"source": self.descriptor.name, "provider": source_name, "status": status, "target": target}
            if bbox:
                attributes["bbox"] = bbox
            if reason:
                attributes["reason"] = reason
            stats = entry.get("stats") if isinstance(entry.get("stats"), dict) else {}
            if stats:
                attributes["stats"] = stats
            total = entry.get("segments_total")
            if isinstance(total, int) and not isinstance(total, bool):
                attributes["segments_total"] = total
            findings.append(Finding(
                entity_type=EntityType.UNKNOWN, value=f"{self.descriptor.name}:{source_name}:{status}",
                attributes=attributes,
                provenance=_prov(self.descriptor, self.descriptor.upstream, 0.4 if status == "ok" else 0.3, raw,
                                 notes=[f"Coverage provider status '{status}' recorded once; nothing was retried or fabricated."]),
            ))
            segments = entry.get("segments") if isinstance(entry.get("segments"), list) else []
            for index, segment in enumerate(segments[:50]):
                if not isinstance(segment, dict):
                    continue
                segment_id = segment.get("id") if isinstance(segment.get("id"), str) and segment.get("id") else f"segment-{index}"
                segment_attributes = {"source": self.descriptor.name, "provider": source_name, "target": target}
                if bbox:
                    segment_attributes["bbox"] = bbox
                length = segment.get("length_m")
                if isinstance(length, (int, float)) and not isinstance(length, bool):
                    segment_attributes["length_m"] = length
                points = segment.get("n_points")
                if isinstance(points, int) and not isinstance(points, bool):
                    segment_attributes["n_points"] = points
                capture_date = segment.get("capture_date")
                if isinstance(capture_date, str) and capture_date:
                    segment_attributes["capture_date"] = capture_date
                for key in ("centroid", "start", "end"):
                    value = segment.get(key)
                    if isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
                        segment_attributes[key] = value
                attribution = segment.get("attribution")
                if isinstance(attribution, str) and attribution:
                    segment_attributes["attribution"] = attribution
                findings.append(Finding(
                    entity_type=EntityType.UNKNOWN, value=f"{self.descriptor.name}:segment:{source_name}:{segment_id}",
                    attributes=segment_attributes,
                    provenance=_prov(self.descriptor, self.descriptor.upstream, 0.5, raw,
                                     notes=["Street-level coverage segment summary (not bulk geometry)."]),
                ))
        run_status = payload.get("status") if isinstance(payload.get("status"), str) else ""
        if payload.get("deadline_exceeded") is True:
            run_status = "deadline_exceeded"
        if run_status in {"invalid_target", "blocked", "error", "deadline_exceeded"}:
            reason = payload.get("error") if isinstance(payload.get("error"), str) else run_status
            findings.append(Finding(
                entity_type=EntityType.UNKNOWN, value=f"{self.descriptor.name}:run:{run_status}",
                attributes={"status": run_status, "target": target, "reason": reason},
                provenance=_prov(self.descriptor, self.descriptor.upstream, 0.3, raw,
                                 notes=[f"Driver recorded run status '{run_status}'; nothing was retried or fabricated."]),
            ))
        return _result(request, self.descriptor, started, findings, stdout, stderr, exit_code)
