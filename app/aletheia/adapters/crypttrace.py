from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from aletheia.core.adapters import Adapter
from aletheia.core.models import (
    AdapterDescriptor, AdapterRunRequest, AdapterRunResult, EntityType, Finding,
    Provenance, SeedType,
)

MAX_ADDRESS_BYTES = 128


def _prov(adapter: AdapterDescriptor, confidence: float, raw: bytes,
          notes: list[str] | None = None) -> Provenance:
    return Provenance(
        tool=adapter.name,
        source_url=adapter.upstream,
        observed_at=datetime.now(timezone.utc),
        confidence=confidence,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version=adapter.version_pin,
        notes=notes or [],
    )


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _text(value, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


class CrypttraceAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="crypttrace",
        license="MIT",
        input_types=[SeedType.CRYPTO_ADDRESS],
        output_types=[EntityType.BLOCKCHAIN_INTEL_RECORD],
        legal_notes=[
            "Bitcoin-only fund-flow trace through the pinned crypttrace 0.22.0 library (MIT, commit cf60a88). The seed address is sent to mempool.space; CoinGecko is contacted for an optional BTC/USD price. No API key is used and no credential is stored.",
            "Upstream labels, risk scores and exchange classifications are heuristics and lead generators, not proof of ownership, identity or wrongdoing. A public-blockchain address is pseudonymous; reaching a labelled address is not attribution.",
            "The upstream fetcher spaces mempool.space calls, caches responses in an ephemeral container-local SQLite file and retries 429s with backoff. The adapter itself never retries or caches. No live target is on file; verification is fixture-based. See docker/crypttrace/RATE_LIMITS.md.",
        ],
        rate_limit="One Bitcoin trace per run; depth 2, branching 3; at most 25 key findings and 25 top counterparties emitted; upstream mempool.space throttle 0.25s and 429 backoff; ephemeral container-local cache. See docker/crypttrace/RATE_LIMITS.md",
        invocation="Docker / CLI",
        version_pin="0.22.0 (commit cf60a88b8be43581186965d160114fdaf3022c62)",
        upstream="https://github.com/bobslayerX/crypttrace",
        network_required=True,
        docker_image="aletheia/crypttrace:v1",
        output_schema={"finding_type": "Finding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type == SeedType.CRYPTO_ADDRESS

    def build_command(self, request: AdapterRunRequest, workspace: Path) -> list[str]:
        address = request.seed.value.strip()
        if not address or "\n" in address or "\r" in address:
            raise ValueError("crypto address must be one non-empty line")
        if len(address.encode("utf-8")) > MAX_ADDRESS_BYTES:
            raise ValueError(f"crypto address exceeds {MAX_ADDRESS_BYTES} bytes")
        (workspace / "address.txt").write_text(address + "\n", encoding="utf-8")
        return ["/work/address.txt"]

    def parse(self, request: AdapterRunRequest, workspace: Path, stdout: str,
              stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        raw = stdout.encode("utf-8", "replace")
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        status = _text(payload.get("status"), 32) or ("ok" if exit_code == 0 else "error")
        subject = _text(payload.get("subject"), 128) or request.seed.value.strip()
        errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
        run_attributes = {
            "source": self.descriptor.name,
            "status": status,
            "subject": subject,
            "chain": _text(payload.get("chain"), 16) or "btc",
            "traced_asset": _text(payload.get("traced_asset"), 16),
            "trace_depth": _number(payload.get("trace_depth")),
            "trace_branching": _number(payload.get("trace_branching")),
            "data_source": _text(payload.get("data_source"), 64),
            "errors": [_text(item, 300) for item in errors[:10] if _text(item, 300)],
        }
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        if summary:
            run_attributes["summary"] = {
                "balance_native": _number(summary.get("balance_native")),
                "native_symbol": _text(summary.get("native_symbol"), 16),
                "transfers_analysed": _number(summary.get("transfers_analysed")),
                "first_seen": _text(summary.get("first_seen"), 32),
                "last_seen": _text(summary.get("last_seen"), 32),
                "label": _text(summary.get("label"), 120),
                "type": _text(summary.get("type"), 32),
                "risk_score": _number(summary.get("risk_score")),
            }
        assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
        if assessment:
            run_attributes["assessment"] = {
                "assessment": _text(assessment.get("assessment"), 800),
                "risk": _number(assessment.get("risk")),
                "confidence": _text(assessment.get("confidence"), 64),
            }
        findings.append(Finding(
            entity_type=EntityType.BLOCKCHAIN_INTEL_RECORD,
            value=f"{self.descriptor.name}:run:{status}",
            attributes=run_attributes,
            provenance=_prov(
                self.descriptor, 0.3, raw,
                notes=["Bitcoin fund-flow trace from a public address; labels are upstream leads, not attribution."],
            ),
        ))

        if status in {"ok", "partial"}:
            seen: set[str] = set()
            key_findings = payload.get("key_findings") if isinstance(payload.get("key_findings"), list) else []
            for index, item in enumerate(key_findings[:25]):
                if not isinstance(item, dict):
                    continue
                address = _text(item.get("address"), 128)
                if not address or address in seen:
                    continue
                seen.add(address)
                attributes = {
                    "source": self.descriptor.name,
                    "subject": subject,
                    "rank": index + 1,
                    "address": address,
                    "label": _text(item.get("label"), 120),
                    "type": _text(item.get("type"), 32),
                    "risk": _number(item.get("risk")),
                    "value_reached": _number(item.get("value_reached")),
                    "symbol": _text(item.get("symbol"), 16),
                    "usd_reached": _number(item.get("usd_reached")),
                    "memo": _text(item.get("memo"), 120),
                }
                findings.append(Finding(
                    entity_type=EntityType.BLOCKCHAIN_INTEL_RECORD,
                    value=f"{self.descriptor.name}:entity:{address}",
                    attributes=attributes,
                    provenance=_prov(
                        self.descriptor, 0.4, raw,
                        notes=["Upstream-labelled counterparty; a lead requiring independent corroboration, not proof of ownership."],
                    ),
                ))
            counterparts = payload.get("top_counterparties") if isinstance(payload.get("top_counterparties"), list) else []
            for index, item in enumerate(counterparts[:25]):
                if not isinstance(item, dict):
                    continue
                address = _text(item.get("address"), 128)
                if not address:
                    continue
                attributes = {
                    "source": self.descriptor.name,
                    "subject": subject,
                    "rank": index + 1,
                    "address": address,
                    "label": _text(item.get("label"), 120),
                    "in": _number(item.get("in")),
                    "out": _number(item.get("out")),
                    "txs": _number(item.get("txs")),
                }
                findings.append(Finding(
                    entity_type=EntityType.BLOCKCHAIN_INTEL_RECORD,
                    value=f"{self.descriptor.name}:counterparty:{address}",
                    attributes=attributes,
                    provenance=_prov(
                        self.descriptor, 0.3, raw,
                        notes=["Direct counterparty aggregated by the upstream report; not a confirmed association."],
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
