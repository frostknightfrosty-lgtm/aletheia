"""Composite public-researcher identity adapter: Wikidata + ORCID.

The runner (docker/researcher_ids/run_researcher_ids.py) performs one bounded
name search against each keyless public API and emits a normalized combined
document. This parser never treats a name match as identity proof; every result
carries a lead-only confidence and the query that produced it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor,
    AdapterRunRequest,
    AdapterRunResult,
    EntityType,
    Finding,
    Provenance,
    SeedType,
)

MAX_NAME_BYTES = 240


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _strings(value: Any, limit: int = 10, width: int = 200) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _text(item, width)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _ids(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("orcid", "viaf", "isni", "gnd"):
        text = _text(value.get(key), 64)
        if text:
            out[key] = text
    return out


def _prov(adapter: AdapterDescriptor, confidence: float, raw: bytes,
          notes: list[str]) -> Provenance:
    return Provenance(
        tool=adapter.name,
        source_url=adapter.upstream,
        observed_at=datetime.now(timezone.utc),
        confidence=confidence,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=notes,
    )


class ResearcherIdsAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="researcher_ids",
        license=(
            "Composite adapter; Wikidata data is CC0 1.0 and ORCID public data is "
            "CC0 1.0, used through each service's published public API terms."
        ),
        input_types=[SeedType.PERSON_NAME],
        output_types=[EntityType.PERSON],
        legal_notes=[
            "Wikidata Action API and the ORCID public API v3.0 are keyless public "
            "services. The adapter sends one bounded name query per run and never "
            "asks for an email address, credential, or private profile field; ORCID "
            "email arrays are discarded by the runner.",
            "A name search is a lead, not identity proof. Common names collide and "
            "neither service asserts that a result is the person the operator meant. "
            "Every finding carries lead-only confidence and the source query.",
            "Only public encyclopedic fields are emitted (labels, descriptions, public "
            "identifiers, occupation, birth date/place, citizenship, public "
            "institutions). No live target is on file; verification is fixture-based. "
            "See docker/researcher_ids/RATE_LIMITS.md.",
        ],
        rate_limit=(
            "One person-name query per run. Wikidata: one wbsearchentities request "
            "(max 5 hits) plus at most two wbgetentities reads (hits and at most 40 "
            "referenced IDs). ORCID: one expanded-search request (max 5 rows). "
            "30-second timeout per request; no retries, pagination, or proxy "
            "rotation. See docker/researcher_ids/RATE_LIMITS.md"
        ),
        invocation="Docker / CLI",
        version_pin="1.0 (public API contracts reviewed 2026-10-20)",
        upstream="https://www.wikidata.org/ and https://pub.orcid.org/",
        network_required=True,
        docker_image="aletheia/researcher-ids:v1",
        output_schema={"finding_type": "Finding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.PERSON_NAME

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        name = request.seed.value.strip()
        if not name or "\n" in name or "\r" in name:
            raise ValueError("person name must be one non-empty line")
        if len(name.encode("utf-8")) > MAX_NAME_BYTES:
            raise ValueError(f"person name exceeds {MAX_NAME_BYTES} bytes")
        name = " ".join(name.split())
        if len(name) < 2:
            raise ValueError("person name must contain at least two characters")
        (workspace / "name.txt").write_text(name + "\n", encoding="utf-8")
        return ["/work/name.txt"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str,
              stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        raw = stdout.encode("utf-8", "replace")
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        status = _text(payload.get("status"), 32) or ("ok" if exit_code == 0 else "error")
        query = _text(payload.get("query"), 120) or request.seed.value.strip()
        errors = _strings(payload.get("errors"), limit=10, width=300)
        wikidata = payload.get("wikidata") if isinstance(payload.get("wikidata"), dict) else {}
        orcid = payload.get("orcid") if isinstance(payload.get("orcid"), dict) else {}
        wiki_results = wikidata.get("results") if isinstance(wikidata.get("results"), list) else []
        orcid_results = orcid.get("results") if isinstance(orcid.get("results"), list) else []
        findings: list[Finding] = [
            Finding(
                entity_type=EntityType.PERSON,
                value=f"{self.descriptor.name}:run:{status}",
                attributes={
                    "source": self.descriptor.name,
                    "status": status,
                    "query": query,
                    "wikidata_status": _text(wikidata.get("status"), 32),
                    "wikidata_num_found": _number(wikidata.get("num_found")),
                    "wikidata_returned": len(wiki_results),
                    "orcid_status": _text(orcid.get("status"), 32),
                    "orcid_num_found": _number(orcid.get("num_found")),
                    "orcid_returned": len(orcid_results),
                    "errors": errors,
                },
                provenance=_prov(
                    self.descriptor, 0.2, raw,
                    ["Public researcher-identity search; name matches are leads, not identity proof."],
                ),
            )
        ]

        if status in {"ok", "partial"}:
            seen: set[str] = set()
            for index, item in enumerate(wiki_results[:5]):
                if not isinstance(item, dict):
                    continue
                qid = _text(item.get("qid"), 32)
                if not qid or qid in seen:
                    continue
                seen.add(qid)
                human = item.get("human") is True
                findings.append(Finding(
                    entity_type=EntityType.PERSON,
                    value=f"{self.descriptor.name}:wikidata:{qid}",
                    attributes={
                        "source": self.descriptor.name,
                        "sub_source": "wikidata",
                        "query": query,
                        "rank": index + 1,
                        "qid": qid,
                        "label": _text(item.get("label"), 200),
                        "description": _text(item.get("description"), 400),
                        "aliases": _strings(item.get("aliases"), 10, 160),
                        "human": human,
                        "instance_of": _strings(item.get("instance_of"), 10, 200),
                        "occupation": _strings(item.get("occupation"), 10, 200),
                        "birth_date": _text(item.get("birth_date"), 32),
                        "birthplace": _strings(item.get("birthplace"), 10, 200),
                        "citizenship": _strings(item.get("citizenship"), 10, 200),
                        "gender": _text(item.get("gender"), 120),
                        "given_name": _text(item.get("given_name"), 160),
                        "family_name": _text(item.get("family_name"), 160),
                        "ids": _ids(item.get("ids")),
                        "website": _text(item.get("website"), 300),
                        "twitter": _text(item.get("twitter"), 120),
                    },
                    provenance=_prov(
                        self.descriptor,
                        0.4 if human else 0.25,
                        raw,
                        ["Wikidata search hit; public encyclopedic metadata and a name match only."],
                    ),
                ))
            for index, item in enumerate(orcid_results[:5]):
                if not isinstance(item, dict):
                    continue
                orcid_id = _text(item.get("orcid"), 32)
                if not orcid_id or orcid_id in seen:
                    continue
                seen.add(orcid_id)
                findings.append(Finding(
                    entity_type=EntityType.PERSON,
                    value=f"{self.descriptor.name}:orcid:{orcid_id}",
                    attributes={
                        "source": self.descriptor.name,
                        "sub_source": "orcid",
                        "query": query,
                        "rank": index + 1,
                        "orcid": orcid_id,
                        "given_name": _text(item.get("given_name"), 120),
                        "family_name": _text(item.get("family_name"), 120),
                        "credit_name": _text(item.get("credit_name"), 160),
                        "other_names": _strings(item.get("other_names"), 10, 160),
                        "institutions": _strings(item.get("institutions"), 10, 200),
                    },
                    provenance=_prov(
                        self.descriptor, 0.4, raw,
                        ["ORCID public-search hit; a name match, not a verified identity."],
                    ),
                ))
        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded" if exit_code == 0 and status == "ok" else "partial",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )
