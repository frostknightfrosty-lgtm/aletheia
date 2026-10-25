"""Local-LLM analyst dossier generation (Phase 18.3).

The generator is deliberately an evidence reader, not an evidence producer. It
loads the run's persisted graph and resolver output, verifies the hash-chained
audit log, writes an evidence-cited dossier directly from those records, and
optionally saves a separate OpenAI-compatible model draft (Ollama by default).
Raw operational audit events are never presented as evidence about the subject.

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

_DISPLAY_ATTRIBUTES = (
    "username",
    "login",
    "handle",
    "screen_name",
    "name",
    "display_name",
    "platform",
    "profile_url",
    "html_url",
    "url",
    "email",
    "phone",
    "domain",
    "ip",
    "ip_address",
    "location",
    "bio",
    "company",
    "blog",
    "created_at",
    "updated_at",
    "avatar_url",
    "followers",
    "following",
    "public_repos",
    "public_gists",
)
_NON_FINDING_STATUSES = {"blocked", "error", "failed", "not_run", "skipped"}

SYSTEM_PROMPT = (
    "You are a cautious OSINT analyst. Write a formal dossier using only facts "
    "explicitly recorded in GRAPH.JSON and RESOLUTION.JSON. Summarize sourced "
    "account candidates and their recorded confidence. Do not claim that matching "
    "accounts belong to the same person unless a confirmed link is recorded. Never "
    "infer or guess a location; report one only when a non-empty, sourced location "
    "attribute is explicitly present in GRAPH.JSON. Cite the adapter and source URL "
    "for every factual claim."
)

RULES = """\
Analyst rules:
- GRAPH.JSON and RESOLUTION.JSON are the only evidence about the subject.
- AUDIT CHAIN INTEGRITY is operational metadata, not evidence about the subject.
- Never treat egress requests, status codes, adapter logs, or audit hashes as subject findings.
- Never infer or guess a location. If no sourced location attribute is recorded in the graph, say no location is recorded.
- For every factual claim, name the adapter (provenance.tool or claim source_adapter) and source URL from the artifacts.
- When a source URL is absent, say "source URL not recorded" and lower the claim's confidence.
- Distinguish confirmed edges from candidates and state the recorded confidence.
- A same-handle match is a candidate, not identity proof. If the artifacts do not support an inference, write that it is unresolved.
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


def _md_text(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _display_attributes(entity: Mapping[str, Any]) -> dict[str, Any]:
    attributes = entity.get("attributes")
    if not isinstance(attributes, Mapping):
        return {}
    return {
        key: attributes[key]
        for key in _DISPLAY_ATTRIBUTES
        if key in attributes and attributes[key] is not None and attributes[key] != ""
    }


def _is_reportable_entity(entity: Mapping[str, Any]) -> bool:
    entity_type = str(entity.get("entity_type", "unknown")).strip().lower()
    canonical = str(entity.get("canonical_value", "")).strip()
    if not canonical or entity_type in {"", "unknown", "finding"}:
        return False
    canonical_lower = canonical.lower()
    if canonical_lower.startswith("finding:") or any(
        marker in canonical_lower for marker in (":error", ":blocked", ":run:")
    ):
        return False
    attributes = entity.get("attributes")
    if isinstance(attributes, Mapping):
        status = str(attributes.get("status", "")).strip().lower()
        if status in _NON_FINDING_STATUSES:
            return False
    return True


def _source_refs(graph: Mapping[str, Any], entity: Mapping[str, Any]) -> list[dict[str, Any]]:
    entity_id = entity.get("entity_id")
    refs: list[dict[str, Any]] = []
    edges = graph.get("edges", [])
    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, Mapping):
                continue
            if edge.get("relationship") != "derived_from" or edge.get("target_entity_id") != entity_id:
                continue
            provenance = edge.get("provenance")
            if not isinstance(provenance, Mapping):
                continue
            source = {
                "tool": provenance.get("tool"),
                "source_url": provenance.get("source_url"),
                "confidence": provenance.get("confidence", edge.get("confidence")),
                "observed_at": provenance.get("observed_at"),
            }
            if source not in refs:
                refs.append(source)
    if refs:
        return refs

    attributes = entity.get("attributes")
    if isinstance(attributes, Mapping):
        tool = attributes.get("tool", attributes.get("source"))
        source_url = attributes.get("source_url")
        if tool or source_url:
            return [
                {
                    "tool": tool,
                    "source_url": source_url,
                    "confidence": attributes.get("confidence"),
                    "observed_at": entity.get("last_seen"),
                }
            ]
    return []


def _prompt_evidence_view(graph: Mapping[str, Any]) -> dict[str, Any]:
    entities = graph.get("entities", [])
    safe_entities = []
    if isinstance(entities, list):
        for entity in entities:
            if not isinstance(entity, Mapping) or not _is_reportable_entity(entity):
                continue
            safe_entities.append(
                {
                    "entity_type": entity.get("entity_type"),
                    "canonical_value": entity.get("canonical_value"),
                    "attributes": _display_attributes(entity),
                    "sources": _source_refs(graph, entity),
                }
            )
    return {"entities": safe_entities}


def _prompt_resolution_view(resolution: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: resolution.get(key)
        for key in (
            "candidate_count",
            "candidates",
            "confirmed_link_count",
            "confirmed_links",
        )
        if key in resolution
    }


def _render_authoritative_dossier(
    run_id: str,
    graph: Mapping[str, Any],
    resolution: Mapping[str, Any],
    integrity: Mapping[str, Any],
) -> str:
    entities = graph.get("entities", [])
    reportable = [
        entity
        for entity in entities
        if isinstance(entity, Mapping) and _is_reportable_entity(entity)
    ] if isinstance(entities, list) else []
    lines = [
        "# Evidence Dossier",
        "",
        f"Run ID: `{_md_text(run_id)}`",
        "",
        "This dossier is rendered from persisted graph values and their recorded provenance. "
        "A matching username or profile is a candidate association, not proof of common identity.",
        "",
        "## Evidence records",
        "",
    ]
    if not reportable:
        lines.extend(["No reportable subject entities were recorded in the graph.", ""])
    for index, entity in enumerate(reportable, 1):
        entity_type = _md_text(entity.get("entity_type", "unknown"))
        canonical = _md_text(entity.get("canonical_value", ""))
        lines.extend([f"### {index}. {entity_type}", "", f"Recorded value: `{canonical}`", ""])
        attributes = _display_attributes(entity)
        if attributes:
            lines.extend(["Recorded attributes:", ""])
            for key, value in attributes.items():
                rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
                lines.append(f"- `{_md_text(key)}`: {_md_text(rendered)}")
            lines.append("")
        sources = _source_refs(graph, entity)
        if sources:
            lines.extend(["Provenance:", ""])
            for source in sources:
                tool = _md_text(source.get("tool") or "tool not recorded")
                source_url = _md_text(source.get("source_url") or "source URL not recorded")
                detail = f"- Adapter: `{tool}`; source: `{source_url}`"
                confidence = source.get("confidence")
                if isinstance(confidence, (int, float)):
                    detail += f"; recorded confidence: `{confidence:g}`"
                observed_at = source.get("observed_at")
                if observed_at:
                    detail += f"; observed: `{_md_text(observed_at)}`"
                lines.append(detail)
            lines.append("")
        else:
            lines.extend(["Provenance: source URL and adapter were not recorded for this entity.", ""])

    candidates = resolution.get("candidate_count", 0)
    confirmed = resolution.get("confirmed_link_count", 0)
    lines.extend(
        [
            "## Resolution summary",
            "",
            f"The resolver recorded `{_md_text(candidates)}` candidate link(s) and "
            f"`{_md_text(confirmed)}` confirmed link(s). Similarity scores are not identity proof.",
            "",
            "## Audit integrity",
            "",
            f"Hash-chain verification result: `{_md_text(integrity.get('valid'))}`.",
            "This is operational integrity metadata; it does not establish the accuracy of a finding.",
            "",
            "## Evidence gaps",
            "",
            "- No location, IP address, or other attribute is inferred from a username. Such a value is reported only if it is explicitly recorded with source provenance above.",
            "- Adapter errors, rate limits, missing credentials, blocked requests, and unavailable sources are not findings about the subject.",
            "- Public profile matches require independent corroboration before being attributed to one person.",
            "",
        ]
    )
    return "\n".join(lines)


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
    integrity: Mapping[str, Any],
) -> str:
    return "\n".join(
        [
            f"Run ID: {run_id}",
            "",
            RULES,
            "### GRAPH.JSON",
            _bounded_json(_prompt_evidence_view(graph), MAX_GRAPH_CHARS),
            "",
            "### RESOLUTION.JSON",
            _bounded_json(_prompt_resolution_view(resolution), MAX_RESOLUTION_CHARS),
            "",
            "### AUDIT CHAIN INTEGRITY (operational metadata only)",
            _bounded_json({"valid": integrity.get("valid")}, 1_000),
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
    """Render the dossier and optionally persist an unverified model draft.

    The evidence-based dossier does not depend on the local model succeeding.
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
    audit_entries = _read_audit(audit_path)
    if not audit_entries:
        raise ValueError(f"AUDIT.jsonl has no entries: {audit_path}")

    integrity = _audit_integrity(safe_id, root)
    prompt = _build_user_prompt(safe_id, graph, resolution, integrity)
    model_name = model or os.getenv("ALETHEIA_LLM_MODEL") or DEFAULT_LLM_MODEL
    draft: str | None = None
    draft_error: str | None = None
    try:
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
        dossier = completion.choices[0].message.content
        if not isinstance(dossier, str) or not dossier.strip():
            raise RuntimeError("local LLM returned an empty dossier")
        draft = dossier.rstrip()
    except Exception as exc:  # noqa: BLE001 - deterministic evidence output remains available
        draft_error = type(exc).__name__

    output_path = run_dir / "dossier.md"
    draft_path = run_dir / "dossier.llm-draft.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if draft is None:
        draft_text = (
            "# UNVERIFIED LLM DRAFT — unavailable\n\n"
            "No language-model draft was generated. "
            f"Failure type: `{_md_text(draft_error or 'unknown')}`.\n"
        )
    else:
        draft_text = (
            "# UNVERIFIED LLM DRAFT — do not use as evidence\n\n"
            "This text is generated by a language model and has not been verified against the graph.\n\n"
            + draft
            + "\n"
        )
    draft_path.write_text(draft_text, encoding="utf-8")
    authoritative = _render_authoritative_dossier(safe_id, graph, resolution, integrity)
    output_path.write_text(authoritative, encoding="utf-8")
    if echo:
        print(f"dossier saved: {output_path}")
        print(f"unverified model draft saved: {draft_path}")
        if draft_error:
            print(f"LLM draft unavailable: {draft_error}")
        print()
        print(authoritative.rstrip())
    return authoritative
