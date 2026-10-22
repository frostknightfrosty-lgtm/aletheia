from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from aletheia.core.graph import Graph
from aletheia.core.models import EntityType, RelationshipType, Seed
from aletheia.phase2.resolution import ResolutionCandidate, seed_attribution


SUPPORTED_STIX_TYPES = {
    EntityType.USERNAME: "user-account",
    EntityType.DOMAIN: "domain-name",
    EntityType.HOST: "domain-name",
    EntityType.URL: "url",
    EntityType.EMAIL: "email-addr",
    EntityType.IP: "ip",
    EntityType.FILE: "file",
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_hash(payload: dict[str, Any]) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))


def _aggregate_confidences(values: list[float]) -> float:
    result = 0.0
    for value in values:
        result = 1 - ((1 - result) * (1 - value))
    return round(result, 6)


def _evidence_for_entity(graph: Graph, entity_id: UUID) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for edge in graph.edges.values():
        if edge.target_entity_id != entity_id or edge.relationship != RelationshipType.DERIVED_FROM:
            continue
        evidence.append({
            "tool": edge.provenance.tool,
            "source_url": edge.provenance.source_url,
            "observed_at": edge.provenance.observed_at.isoformat(),
            "confidence": edge.provenance.confidence,
            "adapter_version": edge.provenance.adapter_version,
            "notes": edge.provenance.notes,
            "finding_id": edge.attributes.get("finding_id"),
        })
    return sorted(evidence, key=lambda x: (x["observed_at"], x["tool"], x.get("finding_id") or ""))


def _claim_confidence(evidence: list[dict[str, Any]]) -> float:
    by_tool: dict[str, float] = {}
    for item in evidence:
        tool = str(item["tool"])
        by_tool[tool] = max(by_tool.get(tool, 0.0), float(item["confidence"]))
    return _aggregate_confidences(list(by_tool.values()))


def build_report_payload(*, run_id: UUID, seed: Seed, graph: Graph, manifest: dict[str, Any],
                         candidates: list[ResolutionCandidate],
                         adapters: list[dict[str, Any]] | None = None,
                         warnings: list[Any] | None = None) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    seeds = [Seed.model_validate(raw) for raw in manifest.get("seeds", [seed.model_dump(mode="json")])]
    attribution = seed_attribution(graph)
    cross_seed_entity_count = sum(1 for indexes in attribution.values() if len(indexes) >= 2)
    claims: list[dict[str, Any]] = []
    for entity in sorted(graph.entities.values(), key=lambda e: (e.entity_type.value, e.canonical_value, str(e.entity_id))):
        evidence = _evidence_for_entity(graph, entity.entity_id)
        # Internal finding nodes are implementation artifacts, not dossier claims.
        if entity.entity_type == EntityType.UNKNOWN and entity.canonical_value.startswith("finding:"):
            continue
        claims.append({
            "claim_id": str(uuid4()),
            "entity_id": str(entity.entity_id),
            "entity_type": entity.entity_type.value,
            "value": entity.canonical_value,
            "attributes": entity.attributes,
            "confidence": _claim_confidence(evidence),
            "evidence": evidence,
        })

    payload: dict[str, Any] = {
        "schema": "aletheia-investigation-report/v1",
        "run_id": str(run_id),
        "generated_at": generated_at.isoformat(),
        "objective": manifest.get("goal"),
        "legal_only": bool(manifest.get("legal_only", True)),
        "seed": seed.model_dump(mode="json"),
        "seeds": [item.model_dump(mode="json") for item in seeds],
        "context_filters": manifest.get("context_filters"),
        "checkpoint_hash": manifest.get("checkpoint_hash"),
        "tool_versions": manifest.get("tool_versions", {}),
        "statistics": {
            "entity_count": len(claims),
            "edge_count": sum(1 for e in graph.edges.values() if e.relationship != RelationshipType.SAME_AS_CANDIDATE),
            "resolution_candidate_count": len(candidates),
            "confirmed_profile_link_count": sum(
                1
                for edge in graph.edges.values()
                if edge.relationship is RelationshipType.SAME_AS_CONFIRMED
                and str(edge.attributes.get("source") or "")
                in {"avatar_phash", "network_overlap", "interactive_label"}
            ),
            "tools_with_evidence": sorted({item["tool"] for claim in claims for item in claim["evidence"]}),
            "seed_count": len(seeds),
            "cross_seed_entity_count": cross_seed_entity_count,
        },
        # Every matching adapter with its outcome, and the reason for each
        # sub-source the adapter could not query (missing keys, retired
        # endpoints, paid-only APIs). Skipped sources are recorded by the
        # adapters themselves during ``resume``; nothing is inferred here.
        "adapters": list(adapters or []),
        "jurisdiction_warnings": [
            item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in (warnings or [])
        ],
        "claims": claims,
        "resolution_candidates": [candidate.to_dict() for candidate in candidates],
        "court_use_note": (
            "This is a provenance-preserving technical report. Its generation does not itself establish legal admissibility; "
            "admissibility, authenticity, and evidentiary weight remain matters for the applicable jurisdiction and procedure."
        ),
    }
    payload["content_hash_sha256"] = _json_hash(payload)
    return payload


def write_json_report(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def write_graphml(graph: Graph, path: Path, *, report_hash: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("graphml", {"xmlns": "http://graphml.graphdrawing.org/xmlns"})
    graph_el = ET.SubElement(root, "graph", {"id": "aletheia", "edgedefault": "directed"})
    for key_id, attr_name in (("d0", "entity_type"), ("d1", "canonical_value"), ("d2", "confidence"), ("d3", "relationship"), ("d4", "tool"), ("d5", "source_url")):
        ET.SubElement(root, "key", {"id": key_id, "for": "all", "attr.name": attr_name, "attr.type": "string"})
    for entity in graph.entities.values():
        node = ET.SubElement(graph_el, "node", {"id": str(entity.entity_id)})
        for key_id, value in (("d0", entity.entity_type.value), ("d1", entity.canonical_value)):
            ET.SubElement(node, "data", {"key": key_id}).text = str(value)
    for edge in graph.edges.values():
        edge_el = ET.SubElement(graph_el, "edge", {
            "id": str(edge.edge_id), "source": str(edge.source_entity_id), "target": str(edge.target_entity_id)
        })
        for key_id, value in (("d2", edge.confidence), ("d3", edge.relationship.value),
                              ("d4", edge.provenance.tool), ("d5", edge.provenance.source_url or "")):
            ET.SubElement(edge_el, "data", {"key": key_id}).text = str(value)
    data = ET.SubElement(graph_el, "data", {"key": "d1"})
    data.text = f"Aletheia report content hash: {report_hash}"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def _stix_id(obj_type: str) -> str:
    return f"{obj_type}--{uuid4()}"


def _stix_sco(entity_type: EntityType, value: str, entity_id: str, evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    stix_type = SUPPORTED_STIX_TYPES.get(entity_type)
    if stix_type is None:
        return None
    obj: dict[str, Any] = {"type": stix_type, "spec_version": "2.1", "id": _stix_id(stix_type)}
    if stix_type == "user-account":
        obj["user_id"] = value
        obj["account_type"] = "username"
    elif stix_type in {"domain-name", "url", "email-addr", "file"}:
        field = {"domain-name": "value", "url": "value", "email-addr": "value"}.get(stix_type)
        if field:
            obj[field] = value
        else:
            obj["name"] = value
    elif stix_type == "ip":
        obj["value"] = value
        import ipaddress
        obj["type"] = "ipv6-addr" if ipaddress.ip_address(value).version == 6 else "ipv4-addr"
        obj["id"] = _stix_id(obj["type"])
    obj["x_aletheia_entity_id"] = entity_id
    obj["x_aletheia_confidence"] = _claim_confidence(evidence)
    obj["x_aletheia_provenance"] = evidence
    return obj


def write_stix2(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    identity_id = _stix_id("identity")
    objects: list[dict[str, Any]] = [{
        "type": "identity", "spec_version": "2.1", "id": identity_id,
        "name": "Aletheia", "identity_class": "organization",
        "description": "Aletheia report generator",
    }]
    for claim in payload["claims"]:
        sco = _stix_sco(EntityType(claim["entity_type"]), claim["value"], claim["entity_id"], claim["evidence"])
        if sco is None:
            continue
        objects.append(sco)
        observed_at = claim["evidence"][0]["observed_at"] if claim["evidence"] else payload["generated_at"]
        observed = {
            "type": "observed-data", "spec_version": "2.1", "id": _stix_id("observed-data"),
            "created_by_ref": identity_id,
            "first_observed": observed_at, "last_observed": observed_at,
            "number_observed": 1, "object_refs": [sco["id"]],
            "x_aletheia_entity_id": claim["entity_id"],
            "x_aletheia_report_hash": payload["content_hash_sha256"],
        }
        objects.append(observed)
    bundle = {
        "type": "bundle",
        "id": _stix_id("bundle"),
        "objects": objects,
    }
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.drawString(18 * mm, 10 * mm, "Aletheia - provenance-preserving technical report")
    canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def write_pdf_report(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title="Aletheia Investigation Report")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["BodyText"], fontSize=6.8, leading=8))
    story: list[Any] = []
    story.append(Paragraph("Aletheia Investigation Report", styles["Title"]))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Technical evidence summary - provenance preserved; not a legal-admissibility determination.", styles["BodyText"]))
    story.append(Spacer(1, 4 * mm))
    meta = [
        ["Run ID", payload["run_id"]],
        ["Generated", payload["generated_at"]],
        ["Seed", f'{payload["seed"]["type"]}:{payload["seed"]["value"]}'],
        ["Legal-only", str(payload["legal_only"])],
        ["Checkpoint hash", str(payload.get("checkpoint_hash"))],
        ["Report content hash", payload["content_hash_sha256"]],
    ]
    t = Table(meta, colWidths=[38 * mm, 142 * mm], repeatRows=0)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Summary", styles["Heading2"]))
    story.append(Paragraph(
        f'Entities: {payload["statistics"]["entity_count"]}; graph edges: {payload["statistics"]["edge_count"]}; '
        f'resolution candidates: {payload["statistics"]["resolution_candidate_count"]}; '
        f'tools with evidence: {", ".join(payload["statistics"]["tools_with_evidence"]) or "none"}.',
        styles["BodyText"]))
    if payload["statistics"].get("seed_count", 1) > 1:
        story.append(Paragraph(
            f'Multi-seed run: {payload["statistics"]["seed_count"]} seeds; entities corroborated by at least two '
            f'seed trees: {payload["statistics"]["cross_seed_entity_count"]}; '
            f'context filters: {json.dumps(payload["context_filters"] or {}, sort_keys=True)}.',
            styles["BodyText"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Adapter Runs", styles["Heading2"]))
    adapter_rows = [["Adapter", "Status", "Skipped sources and reasons"]]
    for entry in payload["adapters"]:
        skip_notes = "; ".join(
            f'{item.get("source", "unknown")}: {item.get("reason", "")}'
            for item in entry.get("skipped_sources", [])
        ) or "none"
        if len(skip_notes) > 400:
            skip_notes = skip_notes[:397] + "..."
        adapter_rows.append([
            str(entry.get("invocation") or entry.get("adapter")), str(entry.get("status")), skip_notes
        ])
    if len(adapter_rows) > 1:
        at = Table(adapter_rows, colWidths=[42 * mm, 22 * mm, 116 * mm], repeatRows=1)
        at.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(at)
    else:
        story.append(Paragraph("No adapter invocations have been recorded for this run.", styles["BodyText"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Claims", styles["Heading2"]))
    claim_rows = [["Type", "Value", "Confidence", "Evidence"]]
    for claim in payload["claims"]:
        claim_rows.append([
            claim["entity_type"], claim["value"], f'{claim["confidence"]:.3f}', str(len(claim["evidence"]))
        ])
    if len(claim_rows) > 1:
        ct = Table(claim_rows, colWidths=[24 * mm, 94 * mm, 25 * mm, 25 * mm], repeatRows=1)
        ct.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(ct)
    else:
        story.append(Paragraph("No dossier claims were generated.", styles["BodyText"]))

    story.append(PageBreak())
    story.append(Paragraph("Provenance Detail", styles["Heading2"]))
    for claim in payload["claims"]:
        story.append(Paragraph(f'{claim["entity_type"]}: {claim["value"]} (confidence {claim["confidence"]:.3f})', styles["Heading3"]))
        for ev in claim["evidence"]:
            src = ev["source_url"] or "local evidence / source URL not applicable"
            line = f'{ev["tool"]} | {ev["observed_at"]} | confidence={ev["confidence"]:.3f} | {src}'
            story.append(Paragraph(line.replace("&", "&amp;"), styles["Tiny"]))
            if ev.get("notes"):
                story.append(Paragraph("Notes: " + "; ".join(ev["notes"]), styles["Tiny"]))
        story.append(Spacer(1, 2 * mm))

    story.append(PageBreak())
    story.append(Paragraph("Resolution Candidates", styles["Heading2"]))
    if payload["resolution_candidates"]:
        rows = [["Left", "Right", "Score", "Decision"]]
        for c in payload["resolution_candidates"]:
            rows.append([c["left_value"], c["right_value"], f'{c["score"]:.3f}', c["decision"]])
        rt = Table(rows, colWidths=[62 * mm, 62 * mm, 22 * mm, 24 * mm], repeatRows=1)
        rt.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(rt)
        story.append(Spacer(1, 4 * mm))
        for c in payload["resolution_candidates"]:
            story.append(Paragraph(
                f'{c["left_value"]} vs {c["right_value"]}: ' + "; ".join(c["explanation"]), styles["Tiny"]))
    else:
        story.append(Paragraph("No fuzzy same-as candidates exceeded the configured threshold.", styles["BodyText"]))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Jurisdiction Warnings (informational)", styles["Heading2"]))
    if payload["jurisdiction_warnings"]:
        story.append(Paragraph(
            "Heuristic signals only; they do not gate the run and are not a legal determination.",
            styles["Small"]))
        for item in payload["jurisdiction_warnings"]:
            line = f'{item.get("kind")}: {item.get("signal")} - {item.get("subject")}'
            story.append(Paragraph(line.replace("&", "&amp;"), styles["Tiny"]))
    else:
        story.append(Paragraph("No jurisdiction-warning signals were matched.", styles["BodyText"]))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Chain of Custody / Integrity", styles["Heading2"]))
    story.append(Paragraph(
        "The report content hash covers the canonical JSON content before artifact files are emitted. "
        "The run checkpoint hash identifies the persisted orchestration checkpoint. Artifact SHA-256 values "
        "should be recorded alongside the exported files when transferred or archived.", styles["Small"]))
    story.append(Paragraph(f'Canonical report content SHA-256: {payload["content_hash_sha256"]}', styles["Small"]))
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return path


def generate_all_reports(*, run_id: UUID, seed: Seed, graph: Graph, manifest: dict[str, Any],
                         candidates: list[ResolutionCandidate], out_dir: Path,
                         adapters: list[dict[str, Any]] | None = None,
                         warnings: list[Any] | None = None) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_report_payload(run_id=run_id, seed=seed, graph=graph, manifest=manifest, candidates=candidates,
                                   adapters=adapters, warnings=warnings)
    json_path = write_json_report(payload, out_dir / "report.json")
    graphml_path = write_graphml(graph, out_dir / "graph.graphml", report_hash=payload["content_hash_sha256"])
    stix_path = write_stix2(payload, out_dir / "report.stix2.json")
    pdf_path = write_pdf_report(payload, out_dir / "report.pdf")

    artifact_hashes = {str(p.name): sha256_file(p) for p in (json_path, graphml_path, stix_path, pdf_path)}
    payload["artifact_sha256"] = {k: v for k, v in artifact_hashes.items() if k != json_path.name}
    # JSON stores the other artifact hashes; its own hash is returned separately to avoid a recursive hash.
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    artifact_hashes[json_path.name] = sha256_file(json_path)
    return {
        "json": str(json_path),
        "pdf": str(pdf_path),
        "graphml": str(graphml_path),
        "stix2": str(stix_path),
        "content_hash_sha256": payload["content_hash_sha256"],
        "json_sha256": artifact_hashes[json_path.name],
        "pdf_sha256": artifact_hashes[pdf_path.name],
        "graphml_sha256": artifact_hashes[graphml_path.name],
        "stix2_sha256": artifact_hashes[stix_path.name],
    }
