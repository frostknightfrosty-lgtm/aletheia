from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from aletheia.core.models import AdapterDescriptor, AdapterRunRequest, AdapterRunResult, AuditEvent, SeedType
from aletheia.core.audit import AuditLogger
from aletheia.core.execution import DockerExecutionError, run_docker


class Adapter(ABC):
    descriptor: AdapterDescriptor

    @abstractmethod
    def supports(self, seed_type: SeedType) -> bool: ...

    @abstractmethod
    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]: ...

    @abstractmethod
    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult: ...

    def run(self, request: AdapterRunRequest, workspace: Path, audit: AuditLogger) -> AdapterRunResult:
        if not request.legal_only:
            raise ValueError("Aletheia adapters require legal_only=true")
        if self.descriptor.requires_authorization_assertion and not request.authorization_assertion:
            raise ValueError(f"{self.descriptor.name} requires an explicit authorization_assertion")
        if not self.supports(request.seed.type):
            raise ValueError(f"{self.descriptor.name} does not support seed type {request.seed.type}")

        workspace.mkdir(parents=True, exist_ok=True)
        command = self.build_command(request, workspace)
        audit.log(AuditEvent(run_id=request.run_id, event_type="adapter_invocation", adapter=self.descriptor.name,
                             command=command, request_meta={"seed_type": request.seed.type, "legal_only": request.legal_only},
                             outcome="started"))
        try:
            result = run_docker(
                image=self.descriptor.docker_image,
                command=command,
                workspace=workspace,
                timeout_seconds=request.timeout_seconds,
                proxy_url=request.proxy_url,
                network=self.descriptor.network_required,
                secret_env=self.descriptor.secret_env,
            )
        except DockerExecutionError as exc:
            audit.log(AuditEvent(run_id=request.run_id, event_type="adapter_invocation", adapter=self.descriptor.name,
                                 command=command, outcome=f"error:{exc}"))
            raise
        parsed = self.parse(request, workspace, result.stdout, result.stderr, result.exit_code)
        audit.log(AuditEvent(run_id=request.run_id, event_type="adapter_complete", adapter=self.descriptor.name,
                             command=command, outcome=parsed.status))
        return parsed
