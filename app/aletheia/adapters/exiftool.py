from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from aletheia.core.adapters import Adapter
from aletheia.core.models import AdapterDescriptor, AdapterRunRequest, AdapterRunResult, EntityType, Finding, Provenance, SeedType


class ExifToolAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="exiftool",
        license="Perl Artistic License / GPL-1-or-later",
        input_types=[SeedType.FILE_PATH],
        output_types=[EntityType.FILE, EntityType.URL, EntityType.UNKNOWN],
        legal_notes=["Local evidence metadata extraction; no network required."],
        rate_limit="Local CPU/I/O only",
        invocation="CLI in dedicated Docker container",
        version_pin="13.59",
        upstream="https://exiftool.org/",
        network_required=False,
        docker_image="aletheia/exiftool:13.59",
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.FILE_PATH

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        src = Path(request.seed.value)
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(f"local evidence file not found: {src}")
        # The orchestrator copies the input into the workspace before invoking the container in production.
        dest = workspace / "input.bin"
        dest.write_bytes(src.read_bytes())
        return ["exiftool", "-j", "-G1", "/work/input.bin"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        try:
            records = json.loads(stdout) if stdout.strip() else []
        except json.JSONDecodeError:
            records = []
        if records and isinstance(records[0], dict):
            metadata = records[0]
            for key, value in metadata.items():
                if key == "SourceFile":
                    continue
                if isinstance(value, (str, int, float, bool)):
                    findings.append(Finding(
                        entity_type=EntityType.UNKNOWN,
                        value=str(value),
                        attributes={"tag": key, "file": request.seed.value},
                        provenance=Provenance(tool=self.descriptor.name, source_url=None,
                                              confidence=0.99, adapter_version=self.descriptor.version_pin,
                                              notes=["Read from local evidence file; field semantics come from ExifTool tag name."]),
                    ))
        findings.insert(0, Finding(
            entity_type=EntityType.FILE,
            value=str(Path(request.seed.value).resolve()),
            attributes={"metadata_read": True},
            provenance=Provenance(tool=self.descriptor.name, confidence=1.0, adapter_version=self.descriptor.version_pin),
            source_kind="seed",
        ))
        return AdapterRunResult(run_id=request.run_id, adapter=self.descriptor, status="succeeded" if exit_code == 0 else "partial",
                                started_at=started, finished_at=datetime.now(timezone.utc), exit_code=exit_code,
                                findings=findings, artifacts=["input.bin"], stderr_tail=stderr[-4000:], stdout_tail=stdout[-4000:])
