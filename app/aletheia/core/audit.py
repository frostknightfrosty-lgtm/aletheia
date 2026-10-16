from __future__ import annotations

from pathlib import Path

from aletheia.core.chain import append
from aletheia.core.models import AuditEvent


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: AuditEvent) -> None:
        append(event, audit_path=self.path)
