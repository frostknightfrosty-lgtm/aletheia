"""Local-LLM analyst dossier generation (Phase 18.3).

The generator is deliberately an evidence reader, not an evidence producer. It
loads the run's persisted graph, resolver output, and hash-chained audit log,
then asks an OpenAI-compatible endpoint (Ollama by default) for a dossier that
cites an adapter and source URL for every claim. The model is never sent a
finding that is not already in the run artifacts.

Only ``graph.json``, ``resolution.json``, and ``AUDIT.jsonl`` are required. A
missing file is a hard error: a dossier is not generated from a partial run.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from aletheia.core import chain

__all__ = ["generate_dossier"]

DEFAULT_LLM_URL = "http://localhost:11434/v1"
DEFAULT_LLM_MODEL = "llama3"

# Keep local-model prompts bounded. These are character caps, not token caps;
# the truncation marker tells the model which sections are incomplete so it can
# avoid claiming evidence it cannot see.
MAX_GRAPH_CHARS = 24_000
MAX_RESOLUTION_CHARS = 16_000
MAX_AUDIT_CHARS = 20_000

SYSTEM_PROMPT = (
    "You are a senior intelligence analyst. Review the following OSINT graph, "
    "resolution candidates, and audit trail. Write a formal dossier. Explain who "
    "this person likely is, their known accounts, their inferred location, and the "
    "confidence of the connections. You MUST cite the specific evidence "
    "(adapter, source URL) for every claim."
)

RULES = """\
Analyst rules:
- Treat the supplied artifacts as the only evidence. Never invent an account, location, or link.
- For every factual claim, name the adapter (provenance.tool or claim source_adapter) and source URL from the artifacts.
- When a source URL is absent, say "source URL not recorded" and lower the claim's confidence.
- Distinguish confirmed edges from candidates and state the recorded confidence.
- If the artifacts do not support an inference, write that it is unresolved.
- Use Markdown headings and finish with an Evidence Gaps section.
"""


def _safe_run_id(run_id: str) -> str:
    value = str(run_id).strip()
    if not value or Path(value).name != value or value in {".", ".."}:
        raise ValueError("run_id must be a single path component")
    return value


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be a JSON object: {path}")
    return payload


def _read_audit(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"AUDIT.jsonl not found: {path}") from exc
    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"AUDIT.jsonl line {line_no} is not valid JSON: {path}"
            ) from exc
        if not isinstance(record, dict):
            raise ValueError(f"AUDIT.jsonl line {line_no} is not an object: {path}")
        entries.append(record)
    return entries


def _bounded_json(payload: Any, max_chars: int) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return (
        text[:max_chars]
        + "\n... [TRUNCATED to the configured prompt budget; cite only visible evidence] ..."
    )


def _audit_integrity(run_id: str, data_dir: Path) -> dict[str, Any]:
    try:
        normalized = UUID(run_id)
    except (TypeError, ValueError):
        return {"valid": None, "reason": "run id is not a UUID"}
    try:
        return chain.verify(normalized, data_root=data_dir)
    except Exception as exc:  # noqa: BLE001 - integrity is context, not generation input
        return {"valid": None, "reason": str(exc)[:300]}


def _build_user_prompt(
    run_id: str,
    graph: Mapping[str, Any],
    resolution: Mapping[str, Any],
    audit: list[dict[str, Any]],
    integrity: Mapping[str, Any],
) -> str:
    return "\n".join(
        [
            f"Run ID: {run_id}",
            "",
            RULES,
            "### GRAPH.JSON",
            _bounded_json(graph, MAX_GRAPH_CHARS),
            "",
            "### RESOLUTION.JSON",
            _bounded_json(resolution, MAX_RESOLUTION_CHARS),
            "",
            "### AUDIT.jsonl (hash-chained adapter and run events)",
            _bounded_json(
                {"integrity": dict(integrity), "entries": audit}, MAX_AUDIT_CHARS
            ),
            "",
            "Write the formal dossier now. Cite adapter and source URL for every claim.",
        ]
    )


def _make_client(llm_url: str) -> Any:
    from openai import OpenAI

    return OpenAI(
        base_url=llm_url,
        api_key=os.getenv("ALETHEIA_LLM_API_KEY", "not-used"),
        timeout=float(os.getenv("ALETHEIA_LLM_TIMEOUT", "300")),
    )


def generate_dossier(
    run_id: str,
    data_dir: str,
    llm_url: str = DEFAULT_LLM_URL,
    *,
    model: str | None = None,
    client: Any | None = None,
    echo: bool = True,
) -> str:
    """Generate, persist, and return ``runs/<run_id>/dossier.md``.

    ``model`` defaults to ``ALETHEIA_LLM_MODEL`` or ``llama3``. ``client`` is
    an injection point for tests; production uses the OpenAI-compatible client
    at ``llm_url`` (Ollama's default is ``http://localhost:11434/v1``).
    """
    safe_id = _safe_run_id(run_id)
    root = Path(data_dir)
    run_dir = root / "runs" / safe_id
    graph_path = root / "graphs" / safe_id / "graph.json"
    if not graph_path.exists():
        graph_path = run_dir / "graph.json"
    resolution_path = run_dir / "resolution.json"
    audit_path = run_dir / "AUDIT.jsonl"

    graph = _read_json(graph_path, "graph.json")
    resolution = _read_json(resolution_path, "resolution.json")
    audit = _read_audit(audit_path)
    if not audit:
        raise ValueError(f"AUDIT.jsonl has no entries: {audit_path}")

    integrity = _audit_integrity(safe_id, root)
    prompt = _build_user_prompt(safe_id, graph, resolution, audit, integrity)
    model_name = model or os.getenv("ALETHEIA_LLM_MODEL") or DEFAULT_LLM_MODEL
    llm = client if client is not None else _make_client(llm_url)
    completion = llm.chat.completions.create(
        model=model_name,
        temperature=0.2,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    try:
        dossier = completion.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise RuntimeError("local LLM returned no dossier content") from exc
    if not isinstance(dossier, str) or not dossier.strip():
        raise RuntimeError("local LLM returned an empty dossier")

    output_path = run_dir / "dossier.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dossier.rstrip() + "\n", encoding="utf-8")
    if echo:
        print(f"dossier saved: {output_path}")
        print()
        print(dossier.rstrip())
    return dossier
