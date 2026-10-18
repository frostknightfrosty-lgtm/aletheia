from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from aletheia.core.adapters import Adapter
from aletheia.core.models import AdapterDescriptor, AdapterRunRequest, AdapterRunResult, EntityType, Finding, Provenance, SeedType


class TheHarvesterAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="theHarvester",
        license="GPL-2.0-only",
        input_types=[SeedType.DOMAIN],
        output_types=[EntityType.HOST, EntityType.EMAIL, EntityType.IP, EntityType.URL],
        legal_notes=[
            "Phase 1 is passive-source collection only.",
            "No DNS resolution, active target probing, path scanning, screenshots, or other target-facing actions in this adapter.",
            "Only select passive providers permitted by the user's license/terms configuration.",
        ],
        rate_limit="Provider-specific; use explicit source list and conservative result cap",
        invocation="CLI in dedicated GPL-2-only Docker container",
        version_pin="4.11.1",
        upstream="https://github.com/laramies/theHarvester",
        network_required=True,
        docker_image="aletheia/theharvester:4.11.1",
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.DOMAIN

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        # crtsh/certspotter are passive sources documented by upstream; choose a small explicit set.
        return ["-d", request.seed.value, "-b", "crtsh,certspotter", "-l", "100", "-f", "/work/harvest"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        jsonl = workspace / "harvest.jsonl"
        if jsonl.exists():
            for raw in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                # Upstream's JSONL is normalized but fields can evolve. Extract only stable candidate strings.
                for key, entity_type in (("host", EntityType.HOST), ("hostname", EntityType.HOST),
                                         ("email", EntityType.EMAIL), ("ip", EntityType.IP), ("url", EntityType.URL)):
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        findings.append(Finding(
                            entity_type=entity_type,
                            value=value,
                            attributes={"domain": request.seed.value},
                            provenance=Provenance(tool=self.descriptor.name, source_url=self.descriptor.upstream,
                                                  confidence=0.80, adapter_version=self.descriptor.version_pin),
                        ))
        findings.insert(0, Finding(
            entity_type=EntityType.DOMAIN,
            value=request.seed.value,
            attributes={"searched": True, "mode": "passive"},
            provenance=Provenance(tool=self.descriptor.name, source_url=self.descriptor.upstream,
                                  confidence=1.0, adapter_version=self.descriptor.version_pin),
            source_kind="seed",
        ))
        status = "succeeded" if exit_code == 0 else "partial"
        return AdapterRunResult(run_id=request.run_id, adapter=self.descriptor, status=status,
                                started_at=started, finished_at=datetime.now(timezone.utc), exit_code=exit_code,
                                findings=findings, artifacts=[str(jsonl)] if jsonl.exists() else [], stderr_tail=stderr[-4000:], stdout_tail=stdout[-4000:])
