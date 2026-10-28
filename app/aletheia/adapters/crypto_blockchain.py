from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
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

# Sub-sources implemented by docker/crypto_blockchain/runner.py. Every one is an
# HTTPS JSON API; the exact endpoint, query-parameter names, authentication and
# documented rate limit of each are recorded in docker/crypto_blockchain/RATE_LIMITS.md.
SUPPORTED_SUB_SOURCES = (
    "mempool-space",
    "blockstream-esplora",
    "blockchair",
    "etherscan-v2",
    "blockcypher",
    "chainabuse",
)

# Candidates with no verifiable request contract are never queried. The runner
# reports each one once per run as a skipped source carrying this exact reason;
# no endpoint, import or version is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "crypttrace": (
        "crypttrace is covered by the separate crypttrace adapter (source #20, "
        "Bitcoin-only); this composite adapter does not query it. It is reported "
        "once per run as a documented skip so the composite source list stays "
        "stable."
    ),
}


class CryptoBlockchainFinding(Finding):
    """Normalized on-chain / address-screening finding from any sub-source."""

    # Subject is stored as the Finding.value field, but also exposed directly
    subject: str | None = None
    # Record type and the observed address are also exposed as direct attributes
    record_type: str | None = None
    address: str | None = None
    address_family: str | None = None
    chain: str | None = None
    identifier: str | None = None
    date: str | None = None

    def __init__(
        self,
        *,
        subject: str,
        source: str,
        record_type: str | None = None,
        address: str | None = None,
        address_family: str | None = None,
        chain: str | None = None,
        identifier: str | None = None,
        date: str | None = None,
        details: dict[str, Any] | None = None,
        raw_evidence: dict[str, Any] | None = None,
        raw_hash: str | None = None,
        timestamp: str | None = None,
        provenance: Provenance | None = None,
    ):
        attributes: dict[str, Any] = {"source": source}
        if record_type:
            attributes["record_type"] = record_type
        if address:
            attributes["address"] = address
        if address_family:
            attributes["address_family"] = address_family
        if chain:
            attributes["chain"] = chain
        if identifier:
            attributes["identifier"] = identifier
        if date:
            attributes["date"] = date
        if details:
            attributes["details"] = details
        if raw_evidence:
            attributes["raw_evidence"] = raw_evidence

        if provenance is None:
            raw_bytes = json.dumps(raw_evidence or {}, sort_keys=True).encode()
            provenance = Provenance(
                tool="crypto_blockchain",
                source_url=f"sub-source:{source}",
                confidence=0.80,
                raw_evidence_sha256=raw_hash or hashlib.sha256(raw_bytes).hexdigest(),
                adapter_version="1.0",
                notes=[f"Normalized from {source} sub-source"],
            )

        # Pass subject as value to the parent Finding model
        super().__init__(
            # Skip/error markers are not domain records (readiness audit 2026-10-25).
            entity_type=EntityType.UNKNOWN if str(subject).endswith((":skipped", ":error")) else EntityType.BLOCKCHAIN_INTEL_RECORD,
            value=subject,
            attributes=attributes,
            provenance=provenance,
            source_kind="derived",
        )
        # Also store subject/record_type/address as direct attributes for convenience
        self.subject = subject
        self.record_type = record_type
        self.address = address
        self.address_family = address_family
        self.chain = chain
        self.identifier = identifier
        self.date = date


def _crypto_provenance(source: str, raw: bytes, notes: list[str]) -> Provenance:
    return Provenance(
        tool="crypto_blockchain",
        source_url=f"sub-source:{source}",
        confidence=0.80,
        raw_evidence_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_version="1.0",
        notes=notes,
    )


def _first_record(data: dict, source: str) -> dict[str, Any] | None:
    """Return the first stored record of a sub-source payload, if any.

    The runner only records a payload when the sub-source produced at least one
    record, so a source with nothing to report contributes no finding rather
    than a negative or empty record.
    """
    records = data.get("records")
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None


_SUBJECT_PREFIXES = {
    "mempool-space": "MEMPOOL",
    "blockstream-esplora": "ESPLORA",
    "blockchair": "BLOCKCHAIR",
    "etherscan-v2": "ETHERSCAN",
    "blockcypher": "BLOCKCYPHER",
    "chainabuse": "CHAINABUSE",
}

_RECORD_TYPES = {
    "mempool-space": "mempool_space_bitcoin_address",
    "blockstream-esplora": "esplora_bitcoin_address",
    "blockchair": "blockchair_address_dashboard",
    "etherscan-v2": "etherscan_ethereum_transaction",
    "blockcypher": "blockcypher_address",
    "chainabuse": "chainabuse_scam_report",
}


def _extract_subject(data: dict, source: str) -> str:
    """Extract a record identifier from the blockchain payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return source
    prefix = _SUBJECT_PREFIXES.get(source, source.upper())
    record_id = record.get("record_id")
    return f"{prefix}:{record_id}" if record_id else f"{prefix}:{source}"


def _extract_record_type(data: dict, source: str) -> str | None:
    if _first_record(data, source) is None:
        return None
    return _RECORD_TYPES.get(source)


def _extract_address(data: dict, source: str) -> str | None:
    query = data.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()
    record = _first_record(data, source)
    return record.get("record_id") or None if record else None


def _extract_address_family(data: dict, source: str) -> str | None:
    family = data.get("address_family")
    return family if isinstance(family, str) and family.strip() else None


def _extract_chain(data: dict, source: str) -> str | None:
    if source == "mempool-space" or source == "blockstream-esplora":
        return "bitcoin"
    if source == "etherscan-v2":
        return "ethereum"
    if source == "blockcypher":
        # BlockCypher names the coin and the network separately (btc/main); the
        # blockchain is the coin, not the network.
        coin = data.get("coin")
        return {"btc": "bitcoin", "eth": "ethereum"}.get(coin) if isinstance(coin, str) else None
    chain = data.get("chain")
    if isinstance(chain, str) and chain.strip():
        return chain.strip()
    return None


def _extract_details(data: dict, source: str) -> dict[str, Any] | None:
    """Extract structured details from the blockchain payload shapes."""
    record = _first_record(data, source)
    if record is None:
        return None
    details: dict[str, Any] = {
        "api_source": data.get("api_source"),
        "api_documentation": data.get("api_documentation"),
        "endpoint": data.get("endpoint"),
        "invocation": data.get("invocation"),
        "address_family": data.get("address_family"),
        "record_count": data.get("record_count"),
        "truncated": data.get("truncated", False),
        "record_id": record.get("record_id"),
        "detail": record.get("detail"),
    }
    if source == "mempool-space":
        details.update(
            {
                "chain_tx_count": record.get("chain_tx_count"),
                "chain_funded_txo_count": record.get("chain_funded_txo_count"),
                "chain_funded_txo_sum": record.get("chain_funded_txo_sum"),
                "chain_spent_txo_count": record.get("chain_spent_txo_count"),
                "chain_spent_txo_sum": record.get("chain_spent_txo_sum"),
                "mempool_tx_count": record.get("mempool_tx_count"),
                "mempool_funded_txo_sum": record.get("mempool_funded_txo_sum"),
            }
        )
    elif source == "blockstream-esplora":
        details.update(
            {
                "chain_tx_count": record.get("chain_tx_count"),
                "chain_funded_txo_count": record.get("chain_funded_txo_count"),
                "chain_funded_txo_sum": record.get("chain_funded_txo_sum"),
                "chain_spent_txo_count": record.get("chain_spent_txo_count"),
                "chain_spent_txo_sum": record.get("chain_spent_txo_sum"),
                "mempool_tx_count": record.get("mempool_tx_count"),
                "mempool_funded_txo_sum": record.get("mempool_funded_txo_sum"),
            }
        )
    elif source == "blockchair":
        details.update(
            {
                "chain": data.get("chain"),
                "context_code": data.get("context_code"),
                "balance": record.get("balance"),
                "transaction_count": record.get("transaction_count"),
                "received": record.get("received"),
                "spent": record.get("spent"),
                "type": record.get("type"),
                "first_seen_receiving": record.get("first_seen_receiving"),
                "last_seen_receiving": record.get("last_seen_receiving"),
                "first_seen_spending": record.get("first_seen_spending"),
                "last_seen_spending": record.get("last_seen_spending"),
            }
        )
    elif source == "etherscan-v2":
        details.update(
            {
                "block_number": record.get("block_number"),
                "time_stamp": record.get("time_stamp"),
                "hash": record.get("hash"),
                "from": record.get("from"),
                "to": record.get("to"),
                "value": record.get("value"),
                "is_error": record.get("is_error"),
                "txreceipt_status": record.get("txreceipt_status"),
                "confirmations": record.get("confirmations"),
                "gas_used": record.get("gas_used"),
            }
        )
    elif source == "blockcypher":
        details.update(
            {
                "coin": data.get("coin"),
                "network": data.get("network"),
                "balance": record.get("balance"),
                "final_balance": record.get("final_balance"),
                "total_received": record.get("total_received"),
                "total_sent": record.get("total_sent"),
                "unconfirmed_balance": record.get("unconfirmed_balance"),
                "n_tx": record.get("n_tx"),
                "unconfirmed_n_tx": record.get("unconfirmed_n_tx"),
                "final_n_tx": record.get("final_n_tx"),
            }
        )
    elif source == "chainabuse":
        details.update(
            {
                "count": data.get("count"),
                "id": record.get("id"),
                "scam_category": record.get("scam_category"),
                "created_at": record.get("created_at"),
                "trusted": record.get("trusted"),
                "checked": record.get("checked"),
                "addresses": record.get("addresses"),
            }
        )
    return details


class CryptoBlockchainAdapter(Adapter):
    descriptor = AdapterDescriptor(
        name="crypto_blockchain",
        license="Composite adapter; sub-sources are the mempool.space REST API, the Blockstream Esplora HTTP API, the Blockchair API, the Etherscan API V2, the BlockCypher API and the Chainabuse Public API v1.2",
        input_types=[SeedType.CRYPTO_ADDRESS],
        output_types=[EntityType.BLOCKCHAIN_INTEL_RECORD],
        legal_notes=[
            "Composite adapter covering the six verified sub-sources of the crypto_blockchain batch: mempool-space (mempool.space REST API), blockstream-esplora (Blockstream Esplora HTTP API), blockchair (Blockchair API), etherscan-v2 (Etherscan API V2), blockcypher (BlockCypher API) and chainabuse (Chainabuse Public API v1.2). The seventh candidate, crypttrace, is dropped and never queried; the runner reports it once per run as a skipped source with the documented reason.",
            "Every endpoint, query-parameter name, authentication requirement, documented rate limit and documentation URL was read from the provider's own official documentation; none was inferred from an example response. All of them are recorded in docker/crypto_blockchain/RATE_LIMITS.md.",
            "The runner classifies the seed as a Bitcoin address, an Ethereum address or unknown and sends it only to the sub-sources whose documentation accepts that chain; a chain mismatch is reported as a documented skip rather than being sent to an endpoint that does not accept it.",
            "Etherscan API V2 requires a free API key and Chainabuse requires an API key. When the matching environment variable is unset the sub-source is reported as a documented skip instead of sending a request the documentation says will be rejected; no credential is stored in this repository and no key is ever printed or recorded in the runner output. Blockchair and BlockCypher keys are optional and are appended as the documented key/token query parameters only when set.",
            "A Chainabuse report is a user or partner submission, not a court finding, and a public on-chain address summary is not attributable to a person or organisation without further evidence. Every finding must be reviewed against the published record before it is relied on.",
            "No sub-source is a locally installed tool, so nothing is executed locally: every sub-source is an HTTPS JSON API queried at most once per run. A run contacts third-party explorers and a screening provider, so it needs authorisation and the assertion is required.",
        ],
        rate_limit="At most one HTTP request per sub-source per run (six requests total), no pagination, records truncated at 25. Documented limits: mempool.space not published (HTTP 429 when exceeded); Blockstream Esplora not published; Blockchair 30 requests/minute (HTTP 430 when blacklisted); Etherscan API V2 free tier 3 calls/second and up to 100,000 calls/day; BlockCypher 3 requests/second unregistered (registered token limits shown by the token object); Chainabuse 10 calls/month on a standard key and up to 5,000 calls/hour for partners. See docker/crypto_blockchain/RATE_LIMITS.md",
        invocation="HTTPS JSON blockchain-explorer and address-screening APIs via dedicated Docker runner (aletheia/crypto-blockchain:v1)",
        version_pin="1.0",
        upstream="https://github.com/frostknightfrosty-lgtm/aletheia/tree/main/docker/crypto_blockchain",
        network_required=True,
        docker_image="aletheia/crypto-blockchain:v1",
        output_schema={"finding_type": "CryptoBlockchainFinding", "item_type": "object"},
        health_check="--health",
        requires_authorization_assertion=True,
        secret_env=[
            "BLOCKCHAIR_API_KEY",
            "BLOCKCYPHER_API_TOKEN",
            "ETHERSCAN_API_KEY",
            "CHAINABUSE_API_KEY",
        ],
    )

    def supports(self, seed_type: SeedType) -> bool:
        return seed_type in {SeedType.CRYPTO_ADDRESS}

    def build_command(self, request: AdapterRunRequest, workspace: Any) -> list[str]:
        # Map seed type to runner input_type
        type_map = {
            SeedType.CRYPTO_ADDRESS: "crypto_address",
        }
        input_type = type_map.get(request.seed.type, "crypto_address")
        return [input_type, request.seed.value]

    def parse(self, request: AdapterRunRequest, workspace: Any, stdout: str, stderr: str, exit_code: int) -> AdapterRunResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []

        if exit_code != 0:
            return AdapterRunResult(
                run_id=request.run_id,
                adapter=self.descriptor,
                status="failed",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=exit_code,
                findings=[],
                stderr_tail=stderr[-4000:],
                stdout_tail=stdout[-4000:],
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return AdapterRunResult(
                run_id=request.run_id,
                adapter=self.descriptor,
                status="partial",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=1,
                findings=[],
                stderr_tail="Runner output was not valid JSON",
                stdout_tail=stdout[-4000:],
            )

        input_type = payload.get("input_type", "")
        input_value = payload.get("input_value", "")
        sources = payload.get("sources", [])

        for src in sources:
            source_name = src.get("source", "unknown")
            skipped = src.get("skipped", False)
            skip_reason = src.get("skip_reason")
            data = src.get("data")
            http_status = src.get("http_status", 0)
            error = src.get("error")
            raw_hash = src.get("raw_hash")
            timestamp = src.get("timestamp")

            if skipped:
                findings.append(CryptoBlockchainFinding(
                    subject=f"{source_name}:skipped",
                    source=source_name,
                    record_type=None,
                    address=None,
                    address_family=None,
                    chain=None,
                    identifier=None,
                    date=None,
                    details={"skipped": True, "reason": skip_reason},
                    raw_evidence={"skipped": True, "reason": skip_reason},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    # Hashed over exactly the recorded raw_evidence, sorted, so the
                    # provenance hash always equals sha256(json.dumps(raw_evidence, sort_keys=True)).
                    provenance=_crypto_provenance(source_name, json.dumps({"skipped": True, "reason": skip_reason}, sort_keys=True).encode(), [f"Skipped: {skip_reason}"]),
                ))
                continue

            if error:
                findings.append(CryptoBlockchainFinding(
                    subject=f"{source_name}:error",
                    source=source_name,
                    record_type=None,
                    address=None,
                    address_family=None,
                    chain=None,
                    identifier=None,
                    date=None,
                    details={"error": error, "http_status": http_status},
                    raw_evidence={"error": error, "http_status": http_status},
                    raw_hash=raw_hash,
                    timestamp=timestamp,
                    provenance=_crypto_provenance(source_name, json.dumps({"error": error, "http_status": http_status}, sort_keys=True).encode(), [f"Error: {error}"]),
                ))
                continue

            if not data:
                continue

            subject = _extract_subject(data, source_name)
            record_type = _extract_record_type(data, source_name)
            details = _extract_details(data, source_name)
            address = _extract_address(data, source_name) or input_value
            address_family = _extract_address_family(data, source_name)
            chain = _extract_chain(data, source_name)

            finding = CryptoBlockchainFinding(
                subject=subject,
                source=source_name,
                record_type=record_type,
                address=address,
                address_family=address_family,
                chain=chain,
                identifier=address,
                date=timestamp[:10] if timestamp else None,
                details=details,
                raw_evidence=data,
                raw_hash=raw_hash,
                timestamp=timestamp,
                provenance=_crypto_provenance(source_name, json.dumps(data, sort_keys=True).encode(), [f"Normalized from {source_name}"]),
            )
            findings.append(finding)

        return AdapterRunResult(
            run_id=request.run_id,
            adapter=self.descriptor,
            status="succeeded",
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            findings=findings,
            stderr_tail=stderr[-4000:],
            stdout_tail=stdout[-4000:],
        )

    def _extract_subject(self, data: dict, source: str) -> str:
        return _extract_subject(data, source)

    def _extract_details(self, data: dict, source: str) -> dict[str, Any] | None:
        return _extract_details(data, source)

    def _extract_record_type(self, data: dict, source: str) -> str | None:
        return _extract_record_type(data, source)


# Auto-register if this module is loaded
def __getattr__(name: str):
    if name == "CryptoBlockchainAdapter":
        return CryptoBlockchainAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
