from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aletheia.core.adapters import Adapter
from aletheia.core.models import (AdapterDescriptor, AdapterRunRequest, AdapterRunResult, EntityType,
                                  Finding, Provenance, SeedType)


class SherlockAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="sherlock",
        license="MIT",
        input_types=[SeedType.USERNAME],
        output_types=[EntityType.USERNAME, EntityType.URL],
        legal_notes=[
            "Public username/site checks only.",
            "Do not use --browse, authentication, CAPTCHA bypass, or other access-control circumvention.",
            "Honor provider rate limits and applicable terms/law.",
        ],
        rate_limit="Upstream/site-specific; default conservative container timeout",
        invocation="CLI in dedicated Docker container",
        version_pin="0.16.2",
        upstream="https://github.com/sherlock-project/sherlock",
        network_required=True,
        docker_image="aletheia/sherlock:0.16.2",
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.USERNAME

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        return ["--no-color", "--output", "/work/sherlock.txt", "--timeout", str(min(request.timeout_seconds, 60)), request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        path = workspace / "sherlock.txt"
        findings: list[Finding] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                url = line.strip()
                if not url or not url.startswith(("http://", "https://")):
                    continue
                findings.append(Finding(
                    entity_type=EntityType.URL,
                    value=url,
                    attributes={"username": request.seed.value, "tool_status": "claimed"},
                    provenance=Provenance(tool=self.descriptor.name, source_url=url,
                                          confidence=0.85, adapter_version=self.descriptor.version_pin),
                ))
        findings.insert(0, Finding(
            entity_type=EntityType.USERNAME,
            value=request.seed.value,
            attributes={"searched": True},
            provenance=Provenance(tool=self.descriptor.name, source_url=self.descriptor.upstream,
                                  confidence=1.0, adapter_version=self.descriptor.version_pin,
                                  notes=["Seed asserted by operator; collector searched public sites."]),
            source_kind="seed",
        ))
        return AdapterRunResult(run_id=request.run_id, adapter=self.descriptor, status="succeeded" if exit_code == 0 else "partial",
                                started_at=started, finished_at=datetime.now(timezone.utc), exit_code=exit_code,
                                findings=findings, artifacts=[str(path)] if path.exists() else [], stderr_tail=stderr[-4000:], stdout_tail=stdout[-4000:])
