from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: UUID) -> Path:
        path = self.root / str(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def manifest_path(self, run_id: UUID) -> Path:
        return self.run_dir(run_id) / "MANIFEST.json"

    def load(self, run_id: UUID) -> dict[str, Any] | None:
        path = self.manifest_path(run_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, run_id: UUID, manifest: dict[str, Any]) -> None:
        path = self.manifest_path(run_id)
        manifest = dict(manifest)
        manifest["updated_at"] = now_iso()
        manifest["checkpoint_hash"] = self._hash_manifest(manifest)
        payload = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        fd, tmp = tempfile.mkstemp(prefix="manifest.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def write_handoff(self, run_id: UUID, objective: str, done: list[str], next_actions: list[str],
                      file_paths: list[str], open_questions: list[str], resume_command: str) -> Path:
        path = self.run_dir(run_id) / "HANDOFF.md"
        done_lines = [f"- {x}" for x in done] or ["- Nothing completed yet."]
        next_lines = [f"- {x}" for x in next_actions] or ["- None recorded."]
        file_lines = [f"- `{x}`" for x in file_paths] or ["- None recorded."]
        question_lines = [f"- {x}" for x in open_questions] or ["- None."]
        text = "\n".join([
            "# Aletheia Handoff",
            "",
            f"Generated: {now_iso()}",
            f"Run ID: `{run_id}`",
            "",
            "## Objective",
            objective,
            "",
            "## Done",
            *done_lines,
            "",
            "## Next",
            *next_lines,
            "",
            "## File paths",
            *file_lines,
            "",
            "## Open questions",
            *question_lines,
            "",
            "## Exact resume command",
            "```bash",
            resume_command,
            "```",
            "",
        ])
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def _hash_manifest(manifest: dict[str, Any]) -> str:
        stripped = {k: v for k, v in manifest.items() if k != "checkpoint_hash"}
        return hashlib.sha256(json.dumps(stripped, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
