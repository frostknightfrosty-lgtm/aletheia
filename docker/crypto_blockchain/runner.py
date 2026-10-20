"""Crypto / blockchain intelligence batch runner.

A composite batch whose sub-sources are public blockchain explorers and one
malicious-address screening API. Every endpoint, query parameter, authentication
requirement, documented rate limit and documentation URL was read from the
sub-source's own official documentation and is recorded in RATE_LIMITS.md next
to this file. No endpoint, parameter name or version was inferred from an
example response.

Standard library only (urllib, json, hashlib, base64, os, re, sys): the image
installs no third-party Python package.

--health prints exactly "ok" on stdout and returns 0 without any network access:
the sub-source inventory (kind, endpoint, whether the optional or required key
is configured) is written to stderr as one JSON line, because the Docker
integration smoke case asserts stdout.strip() == "ok". No secret value is ever
printed or recorded.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

# -- sub-sources ---------------------------------------------------------------

# Implemented sub-sources. All six are HTTPS JSON APIs; each one is queried at
# most once per run.
SUPPORTED_SUB_SOURCES = (
    "mempool-space",
    "blockstream-esplora",
    "blockchair",
    "etherscan-v2",
    "blockcypher",
    "chainabuse",
)

# Not queried by this composite. crypttrace is covered by its own separate
# adapter (Bitcoin-only); it is reported once per run as an auditable skip so
# the composite source list stays stable, and no endpoint is invented for it.
UNSUPPORTED_SUB_SOURCES: dict[str, str] = {
    "crypttrace": (
        "crypttrace is covered by the separate crypttrace adapter (source #20, "
        "Bitcoin-only); this composite adapter does not query it. It is reported "
        "once per run as a documented skip so the composite source list stays "
        "stable."
    ),
}

# -- documented endpoints ------------------------------------------------------
#
# Every constant below is the verbatim endpoint from the sub-source's own
# documentation; the docs URL for each one is recorded next to it and in
# RATE_LIMITS.md.

# mempool.space REST API. The project's own REST reference documents the address
# call as https://mempool.space/api/address/<address> and the transaction call as
# https://mempool.space/api/tx/<txid>.
MEMPOOL_SPACE_DOCS = "https://mempool.space/docs/api/rest"
MEMPOOL_SPACE_ADDRESS_URL = "https://mempool.space/api/address/{address}"
MEMPOOL_SPACE_TX_URL = "https://mempool.space/api/tx/{txid}"

# Blockstream Esplora HTTP API. The public Bitcoin instance is documented as
# https://blockstream.info/api/ and serves GET /address/:address and GET /tx/:txid.
BLOCKSTREAM_ESPLORA_DOCS = "https://github.com/Blockstream/esplora/blob/master/API.md"
BLOCKSTREAM_ESPLORA_BASE = "https://blockstream.info/api"
BLOCKSTREAM_ESPLORA_ADDRESS_URL = BLOCKSTREAM_ESPLORA_BASE + "/address/{address}"
BLOCKSTREAM_ESPLORA_TX_URL = BLOCKSTREAM_ESPLORA_BASE + "/tx/{txid}"

# Blockchair API. The documented address dashboard is
# https://api.blockchair.com/{chain}/dashboards/address/{address} and the
# transaction dashboard is /{chain}/dashboards/transaction/{hash}. The optional
# key is appended as ?key=<key>.
BLOCKCHAIR_DOCS = "https://blockchair.com/api/docs"
BLOCKCHAIR_BITCOIN_ADDRESS_URL = "https://api.blockchair.com/bitcoin/dashboards/address/{address}"
BLOCKCHAIR_ETHEREUM_ADDRESS_URL = "https://api.blockchair.com/ethereum/dashboards/address/{address}"
BLOCKCHAIR_BITCOIN_TX_URL = "https://api.blockchair.com/bitcoin/dashboards/transaction/{txid}"
BLOCKCHAIR_ETHEREUM_TX_URL = "https://api.blockchair.com/ethereum/dashboards/transaction/{txid}"

# Etherscan API V2. The documented call is
# GET https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist&address=<address>...&apikey=<key>
# (the make-your-first-call page documents chainid/module/action/address/tag/apikey).
ETHERSCAN_V2_DOCS = "https://docs.etherscan.io/make-your-first-call"
ETHERSCAN_V2_API_URL = "https://api.etherscan.io/v2/api"

# BlockCypher. The documented Address Endpoint is
# https://api.blockcypher.com/v1/{coin}/{chain}/addrs/{address}; the documented
# token may be appended as ?token=<token>.
BLOCKCYPHER_DOCS = "https://www.blockcypher.com/dev/bitcoin/"
BLOCKCYPHER_BITCOIN_ADDRESS_URL = "https://api.blockcypher.com/v1/btc/main/addrs/{address}"
BLOCKCYPHER_ETHEREUM_ADDRESS_URL = "https://api.blockcypher.com/v1/eth/main/addrs/{address}"
BLOCKCYPHER_BITCOIN_TX_URL = "https://api.blockcypher.com/v1/btc/main/txs/{txid}"
BLOCKCYPHER_ETHEREUM_TX_URL = "https://api.blockcypher.com/v1/eth/main/txs/{txid}"

# Chainabuse Public API v1.2. The documented Get Reports call is
# GET https://api.chainabuse.com/v0/reports?address=<address> with HTTP Basic
# authentication carrying the API key as the username (password may be blank).
CHAINABUSE_DOCS = "https://docs.chainabuse.com/reference/reports-1"
CHAINABUSE_REPORTS_URL = "https://api.chainabuse.com/v0/reports"

# This adapter's own environment-variable names. None of these is published by a
# vendor; each one maps to the credential the vendor's own documentation
# requires (an apikey query parameter, a key query parameter, a token query
# parameter, or HTTP Basic auth). The name is the only thing this adapter
# chooses; no vendor fact is invented.
BLOCKCHAIR_API_KEY_ENV = "BLOCKCHAIR_API_KEY"
BLOCKCYPHER_API_TOKEN_ENV = "BLOCKCYPHER_API_TOKEN"
ETHERSCAN_API_KEY_ENV = "ETHERSCAN_API_KEY"
CHAINABUSE_API_KEY_ENV = "CHAINABUSE_API_KEY"

# Documented human-readable invocation of each sub-source, verbatim from its docs.
MEMPOOL_SPACE_INVOCATION = "GET https://mempool.space/api/address/<address>"
BLOCKSTREAM_ESPLORA_INVOCATION = "GET https://blockstream.info/api/address/<address>"
BLOCKCHAIR_INVOCATION = "GET https://api.blockchair.com/<chain>/dashboards/address/<address>"
ETHERSCAN_V2_INVOCATION = (
    "GET https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist&address=<address>"
)
BLOCKCYPHER_INVOCATION = "GET https://api.blockcypher.com/v1/<coin>/main/addrs/<address>"
CHAINABUSE_INVOCATION = "GET https://api.chainabuse.com/v0/reports?address=<address>"

USER_AGENT = "Aletheia/0.9.0 (crypto-blockchain)"

# One run answers a single seed. Store at most this many records per sub-source.
MAX_RECORDS = 25

# Cap any single response so a misbehaving endpoint cannot exhaust memory.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

HTTP_TIMEOUT_SECONDS = 30

# Documented Bitcoin and Ethereum address shapes. Anything else is reported as a
# documented skip for the chain-specific sub-sources instead of being sent to an
# endpoint whose documentation does not accept it.
BITCOIN_ADDRESS_RE = re.compile(
    r"^(?:bc1[023456789acdefghjklmnpqrstuvwxyz]{11,71}|[13][1-9A-HJ-NP-Za-km-z]{25,34})$"
)
ETHEREUM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _address_family(value: str) -> str:
    """Classify a seed as a Bitcoin address, an Ethereum address, or unknown."""
    text = _clean(value)
    if ETHEREUM_ADDRESS_RE.match(text):
        return "ethereum"
    if BITCOIN_ADDRESS_RE.match(text):
        return "bitcoin"
    return "unknown"


# -- HTTP ----------------------------------------------------------------------


def _fetch_json(
    url: str,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[Any, int, str | None]:
    """Fetch one JSON document. Returns (data, http_status, error).

    Any credential is carried inside the URL or the request headers by the
    caller; neither the URL nor the headers are ever printed by this runner.
    """
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json,*/*"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            status = response.status
            if len(body) > max_bytes:
                return None, status, (
                    "Response exceeded the " + str(max_bytes // (1024 * 1024)) + " MB safety limit"
                )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, exc.code, "HTTP " + str(exc.code) + ": " + detail[:500]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, 0, type(exc).__name__ + ": " + str(exc)
    try:
        return json.loads(body.decode("utf-8", errors="replace")), status, None
    except json.JSONDecodeError as exc:
        return None, status, "JSON decode error: " + str(exc)


class SourceResult:
    def __init__(
        self,
        name: str,
        data: dict | list | None = None,
        http_status: int = 0,
        error: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
    ):
        self.name = name
        self.data = data
        self.http_status = http_status
        self.error = error
        self.skipped = skipped
        self.skip_reason = skip_reason
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.raw_hash = _sha256(json.dumps(data, sort_keys=True).encode()) if data else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.name,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "timestamp": self.timestamp,
            "http_status": self.http_status,
            "error": self.error,
            "raw_hash": self.raw_hash,
            "data": self.data,
        }


def _skip(name: str, reason: str) -> SourceResult:
    """A sub-source that is deliberately not queried this run, with its reason."""
    return SourceResult(name, skipped=True, skip_reason=reason)


def _payload(
    *,
    api_source: str,
    api_documentation: str,
    endpoint: str,
    invocation: str,
    query: str,
    address_family: str,
    records: list[dict[str, Any]],
    total: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "api_source": api_source,
        "api_documentation": api_documentation,
        "endpoint": endpoint,
        "invocation": invocation,
        "query": query,
        "address_family": address_family,
        "record_count": total,
        "truncated": total > len(records),
    }
    if extra:
        data.update(extra)
    data["records"] = records
    return data


# -- mempool.space -------------------------------------------------------------


def query_mempool_space(value: str) -> SourceResult:
    family = _address_family(value)
    if family != "bitcoin":
        return _skip(
            "mempool-space",
            "mempool.space documents Bitcoin addresses only (any P2PKH, P2SH, Bech32 or Bech32m "
            "address), and the supplied value is not a Bitcoin address.",
        )
    endpoint = MEMPOOL_SPACE_ADDRESS_URL.format(address=urllib.parse.quote(value, safe=""))
    data, status, error = _fetch_json(endpoint)
    if error:
        return SourceResult("mempool-space", http_status=status, error=error)
    if not isinstance(data, dict) or "address" not in data:
        return SourceResult("mempool-space", http_status=status, error="Unexpected response shape from mempool.space")

    chain_stats = data.get("chain_stats") if isinstance(data.get("chain_stats"), dict) else {}
    mempool_stats = data.get("mempool_stats") if isinstance(data.get("mempool_stats"), dict) else {}
    tx_count = chain_stats.get("tx_count")
    record = {
        "record_id": _clean(data.get("address")) or value,
        "detail": (
            "mempool.space address summary: "
            + _clean(tx_count)
            + " confirmed transactions, funded "
            + _clean(chain_stats.get("funded_txo_sum"))
            + " sat, spent "
            + _clean(chain_stats.get("spent_txo_sum"))
            + " sat"
        ),
        "chain_tx_count": chain_stats.get("tx_count"),
        "chain_funded_txo_count": chain_stats.get("funded_txo_count"),
        "chain_funded_txo_sum": chain_stats.get("funded_txo_sum"),
        "chain_spent_txo_count": chain_stats.get("spent_txo_count"),
        "chain_spent_txo_sum": chain_stats.get("spent_txo_sum"),
        "mempool_tx_count": mempool_stats.get("tx_count"),
        "mempool_funded_txo_sum": mempool_stats.get("funded_txo_sum"),
    }
    payload = _payload(
        api_source="mempool.space REST API (Bitcoin)",
        api_documentation=MEMPOOL_SPACE_DOCS,
        endpoint=endpoint,
        invocation=MEMPOOL_SPACE_INVOCATION,
        query=value,
        address_family=family,
        records=[record],
        total=1,
    )
    return SourceResult("mempool-space", data=payload, http_status=status)


# -- Blockstream Esplora -------------------------------------------------------


def query_blockstream_esplora(value: str) -> SourceResult:
    family = _address_family(value)
    if family != "bitcoin":
        return _skip(
            "blockstream-esplora",
            "The Blockstream Esplora API's public Bitcoin instance documents GET /address/:address for "
            "Bitcoin addresses, and the supplied value is not a Bitcoin address.",
        )
    endpoint = BLOCKSTREAM_ESPLORA_ADDRESS_URL.format(address=urllib.parse.quote(value, safe=""))
    data, status, error = _fetch_json(endpoint)
    if error:
        return SourceResult("blockstream-esplora", http_status=status, error=error)
    if not isinstance(data, dict) or "address" not in data:
        return SourceResult(
            "blockstream-esplora", http_status=status, error="Unexpected response shape from Blockstream Esplora"
        )

    chain_stats = data.get("chain_stats") if isinstance(data.get("chain_stats"), dict) else {}
    mempool_stats = data.get("mempool_stats") if isinstance(data.get("mempool_stats"), dict) else {}
    record = {
        "record_id": _clean(data.get("address")) or value,
        "detail": (
            "Blockstream Esplora address summary: "
            + _clean(chain_stats.get("tx_count"))
            + " confirmed transactions, funded "
            + _clean(chain_stats.get("funded_txo_sum"))
            + " sat, spent "
            + _clean(chain_stats.get("spent_txo_sum"))
            + " sat"
        ),
        "chain_tx_count": chain_stats.get("tx_count"),
        "chain_funded_txo_count": chain_stats.get("funded_txo_count"),
        "chain_funded_txo_sum": chain_stats.get("funded_txo_sum"),
        "chain_spent_txo_count": chain_stats.get("spent_txo_count"),
        "chain_spent_txo_sum": chain_stats.get("spent_txo_sum"),
        "mempool_tx_count": mempool_stats.get("tx_count"),
        "mempool_funded_txo_sum": mempool_stats.get("funded_txo_sum"),
    }
    payload = _payload(
        api_source="Blockstream Esplora HTTP API (Bitcoin)",
        api_documentation=BLOCKSTREAM_ESPLORA_DOCS,
        endpoint=endpoint,
        invocation=BLOCKSTREAM_ESPLORA_INVOCATION,
        query=value,
        address_family=family,
        records=[record],
        total=1,
    )
    return SourceResult("blockstream-esplora", data=payload, http_status=status)


# -- Blockchair ----------------------------------------------------------------


def query_blockchair(value: str) -> SourceResult:
    family = _address_family(value)
    if family == "bitcoin":
        template = BLOCKCHAIR_BITCOIN_ADDRESS_URL
        chain = "bitcoin"
    elif family == "ethereum":
        template = BLOCKCHAIR_ETHEREUM_ADDRESS_URL
        chain = "ethereum"
    else:
        return _skip(
            "blockchair",
            "Blockchair documents an address dashboard per supported chain; the supplied value is neither "
            "a Bitcoin address nor a 0x-prefixed 40-hex Ethereum address, so no documented dashboard "
            "endpoint applies.",
        )

    encoded = urllib.parse.quote(value, safe="")
    endpoint = template.format(address=encoded)
    redacted = endpoint
    api_key = os.environ.get(BLOCKCHAIR_API_KEY_ENV, "").strip()
    if api_key:
        # The key is appended as ?key=<key> exactly as documented; the recorded
        # endpoint never contains it.
        endpoint = endpoint + "?key=" + urllib.parse.quote(api_key, safe="")
        redacted = template.format(address=encoded) + "?key=<configured>"

    data, status, error = _fetch_json(endpoint)
    if error:
        return SourceResult("blockchair", http_status=status, error=error)

    entry: dict[str, Any] = {}
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        candidate = data["data"].get(value)
        if isinstance(candidate, dict):
            entry = candidate
    context = data.get("context") if isinstance(data, dict) and isinstance(data.get("context"), dict) else {}
    if not entry:
        context_error = _clean(context.get("error")) if isinstance(context, dict) else ""
        if context_error:
            return SourceResult("blockchair", http_status=status, error="Blockchair error: " + context_error)
        return SourceResult("blockchair", http_status=status)

    address_info = entry.get("address") if isinstance(entry.get("address"), dict) else {}
    record = {
        "record_id": value,
        "detail": (
            "Blockchair "
            + chain
            + " address dashboard: balance "
            + _clean(address_info.get("balance"))
            + ", transaction_count "
            + _clean(address_info.get("transaction_count"))
        ),
        "balance": address_info.get("balance"),
        "transaction_count": address_info.get("transaction_count"),
        "received": address_info.get("received"),
        "spent": address_info.get("spent"),
        "type": address_info.get("type"),
        "first_seen_receiving": address_info.get("first_seen_receiving"),
        "last_seen_receiving": address_info.get("last_seen_receiving"),
        "first_seen_spending": address_info.get("first_seen_spending"),
        "last_seen_spending": address_info.get("last_seen_spending"),
    }
    payload = _payload(
        api_source="Blockchair API (" + chain + " address dashboard)",
        api_documentation=BLOCKCHAIR_DOCS,
        endpoint=redacted,
        invocation=BLOCKCHAIR_INVOCATION,
        query=value,
        address_family=family,
        records=[record],
        total=1,
        extra={"chain": chain, "context_code": context.get("code") if isinstance(context, dict) else None},
    )
    return SourceResult("blockchair", data=payload, http_status=status)


# -- Etherscan API V2 ----------------------------------------------------------


def query_etherscan_v2(value: str) -> SourceResult:
    api_key = os.environ.get(ETHERSCAN_API_KEY_ENV, "").strip()
    if not api_key:
        return _skip(
            "etherscan-v2",
            "ETHERSCAN_API_KEY is not set. The Etherscan API V2 documents a mandatory apikey query "
            'parameter and answers NOTOK "Missing/Invalid API Key" without one, so the sub-source is not '
            "queried.",
        )
    family = _address_family(value)
    if family != "ethereum":
        return _skip(
            "etherscan-v2",
            "This adapter queries the Etherscan API V2 account/txlist endpoint on chainid=1 (Ethereum), whose "
            "documented address parameter takes an EVM address; the supplied value is not a 0x-prefixed "
            "40-hex Ethereum address.",
        )

    params = {
        "chainid": "1",
        "module": "account",
        "action": "txlist",
        "address": value,
        "page": "1",
        "offset": str(MAX_RECORDS),
        "sort": "desc",
        "apikey": api_key,
    }
    endpoint = ETHERSCAN_V2_API_URL + "?" + urllib.parse.urlencode(params)
    redacted = ETHERSCAN_V2_API_URL + "?" + urllib.parse.urlencode({**params, "apikey": "<configured>"})
    data, status, error = _fetch_json(endpoint)
    if error:
        return SourceResult("etherscan-v2", http_status=status, error=error)
    if not isinstance(data, dict):
        return SourceResult("etherscan-v2", http_status=status, error="Unexpected response shape from Etherscan")

    result = data.get("result")
    if _clean(data.get("status")) != "1":
        message = _clean(data.get("message"))
        if isinstance(result, list) and not result:
            # Documented "No transactions found" answer: a valid empty result.
            return SourceResult("etherscan-v2", http_status=status)
        return SourceResult(
            "etherscan-v2",
            http_status=status,
            error="Etherscan API V2 error: " + (message or "unknown error"),
        )

    transactions = result if isinstance(result, list) else []
    records: list[dict[str, Any]] = []
    for tx in transactions[:MAX_RECORDS]:
        if not isinstance(tx, dict):
            continue
        records.append(
            {
                "record_id": _clean(tx.get("hash")),
                "detail": (
                    "Ethereum transaction "
                    + _clean(tx.get("hash"))
                    + " from "
                    + _clean(tx.get("from"))
                    + " to "
                    + _clean(tx.get("to"))
                    + " value "
                    + _clean(tx.get("value"))
                    + " wei"
                ),
                "block_number": tx.get("blockNumber"),
                "time_stamp": tx.get("timeStamp"),
                "hash": tx.get("hash"),
                "from": tx.get("from"),
                "to": tx.get("to"),
                "value": tx.get("value"),
                "is_error": tx.get("isError"),
                "txreceipt_status": tx.get("txreceipt_status"),
                "confirmations": tx.get("confirmations"),
                "gas_used": tx.get("gasUsed"),
            }
        )

    if not records:
        return SourceResult("etherscan-v2", http_status=status)

    payload = _payload(
        api_source="Etherscan API V2 (account/txlist, chainid=1)",
        api_documentation=ETHERSCAN_V2_DOCS,
        endpoint=redacted,
        invocation=ETHERSCAN_V2_INVOCATION,
        query=value,
        address_family=family,
        records=records,
        total=len(transactions),
    )
    return SourceResult("etherscan-v2", data=payload, http_status=status)


# -- BlockCypher ---------------------------------------------------------------


def query_blockcypher(value: str) -> SourceResult:
    family = _address_family(value)
    if family == "bitcoin":
        template = BLOCKCYPHER_BITCOIN_ADDRESS_URL
        coin = "btc"
    elif family == "ethereum":
        template = BLOCKCYPHER_ETHEREUM_ADDRESS_URL
        coin = "eth"
    else:
        return _skip(
            "blockcypher",
            "The BlockCypher Address Endpoint documents one coin/chain per request (this adapter queries "
            "btc/main and eth/main); the supplied value is neither a Bitcoin address nor a 0x-prefixed "
            "40-hex Ethereum address.",
        )

    endpoint = template.format(address=urllib.parse.quote(value, safe=""))
    redacted = endpoint
    token = os.environ.get(BLOCKCYPHER_API_TOKEN_ENV, "").strip()
    if token:
        # Documented as "Adding your token as URL parameter": ?token=<token>.
        endpoint = endpoint + "?token=" + urllib.parse.quote(token, safe="")
        redacted = template.format(address=urllib.parse.quote(value, safe="")) + "?token=<configured>"

    data, status, error = _fetch_json(endpoint)
    if error:
        return SourceResult("blockcypher", http_status=status, error=error)
    if not isinstance(data, dict) or "address" not in data:
        return SourceResult("blockcypher", http_status=status, error="Unexpected response shape from BlockCypher")

    record = {
        "record_id": _clean(data.get("address")) or value,
        "detail": (
            "BlockCypher "
            + coin
            + " address: balance "
            + _clean(data.get("balance"))
            + ", final_balance "
            + _clean(data.get("final_balance"))
            + ", n_tx "
            + _clean(data.get("n_tx"))
        ),
        "balance": data.get("balance"),
        "final_balance": data.get("final_balance"),
        "total_received": data.get("total_received"),
        "total_sent": data.get("total_sent"),
        "unconfirmed_balance": data.get("unconfirmed_balance"),
        "n_tx": data.get("n_tx"),
        "unconfirmed_n_tx": data.get("unconfirmed_n_tx"),
        "final_n_tx": data.get("final_n_tx"),
    }
    payload = _payload(
        api_source="BlockCypher Address Endpoint (" + coin + "/main)",
        api_documentation=BLOCKCYPHER_DOCS,
        endpoint=redacted,
        invocation=BLOCKCYPHER_INVOCATION,
        query=value,
        address_family=family,
        records=[record],
        total=1,
        extra={"coin": coin, "network": "main"},
    )
    return SourceResult("blockcypher", data=payload, http_status=status)


# -- Chainabuse ----------------------------------------------------------------


def query_chainabuse(value: str) -> SourceResult:
    api_key = os.environ.get(CHAINABUSE_API_KEY_ENV, "").strip()
    if not api_key:
        return _skip(
            "chainabuse",
            "CHAINABUSE_API_KEY is not set. The Chainabuse Get Reports API documents HTTP Basic "
            "authentication with the API key as the username (the password may be blank) and answers "
            'HTTP 401 {"message":"Invalid credentials"} without credentials, so the sub-source is not queried.',
        )

    endpoint = CHAINABUSE_REPORTS_URL + "?" + urllib.parse.urlencode({"address": value})
    credentials = base64.b64encode((api_key + ":").encode("utf-8")).decode("ascii")
    data, status, error = _fetch_json(endpoint, headers={"Authorization": "Basic " + credentials})
    if error:
        return SourceResult("chainabuse", http_status=status, error=error)
    if not isinstance(data, dict):
        return SourceResult("chainabuse", http_status=status, error="Unexpected response shape from Chainabuse")

    reports = data.get("reports")
    if not isinstance(reports, list) or not reports:
        return SourceResult("chainabuse", http_status=status)

    records: list[dict[str, Any]] = []
    for report in reports[:MAX_RECORDS]:
        if not isinstance(report, dict):
            continue
        addresses = report.get("addresses") if isinstance(report.get("addresses"), list) else []
        records.append(
            {
                "record_id": _clean(report.get("id")),
                "detail": (
                    "Chainabuse report "
                    + _clean(report.get("id"))
                    + " category "
                    + _clean(report.get("scamCategory"))
                    + " created "
                    + _clean(report.get("createdAt"))
                ),
                "id": report.get("id"),
                "scam_category": report.get("scamCategory"),
                "created_at": report.get("createdAt"),
                "trusted": report.get("trusted"),
                "checked": report.get("checked"),
                "addresses": addresses,
            }
        )

    payload = _payload(
        api_source="Chainabuse Public API (v1.2 Get Reports)",
        api_documentation=CHAINABUSE_DOCS,
        endpoint=endpoint,
        invocation=CHAINABUSE_INVOCATION,
        query=value,
        address_family=_address_family(value),
        records=records,
        total=len(reports),
        extra={"count": data.get("count")},
    )
    return SourceResult("chainabuse", data=payload, http_status=status)


# -- crypttrace (dropped) ------------------------------------------------------


def query_crypttrace(value: str) -> SourceResult:
    """Never queried: crypttrace documents no importable API.

    The runner reports the documented reason so the candidate is an auditable
    skip rather than a silent omission, and no endpoint is invented for it.
    """
    return _skip("crypttrace", UNSUPPORTED_SUB_SOURCES["crypttrace"])


# -- health --------------------------------------------------------------------


def _health_inventory() -> dict[str, Any]:
    """Describe sub-source availability without any network call."""
    entries: list[dict[str, Any]] = []
    for name, endpoint, credential_env in (
        ("mempool-space", MEMPOOL_SPACE_ADDRESS_URL, None),
        ("blockstream-esplora", BLOCKSTREAM_ESPLORA_ADDRESS_URL, None),
        ("blockchair", BLOCKCHAIR_BITCOIN_ADDRESS_URL, BLOCKCHAIR_API_KEY_ENV),
        ("etherscan-v2", ETHERSCAN_V2_API_URL, ETHERSCAN_API_KEY_ENV),
        ("blockcypher", BLOCKCYPHER_BITCOIN_ADDRESS_URL, BLOCKCYPHER_API_TOKEN_ENV),
        ("chainabuse", CHAINABUSE_REPORTS_URL, CHAINABUSE_API_KEY_ENV),
    ):
        entries.append(
            {
                "source": name,
                "kind": "http_api",
                "usable": True,
                "endpoint": endpoint,
                "credential_env": credential_env,
                "credential_configured": (
                    bool(os.environ.get(credential_env, "").strip()) if credential_env else None
                ),
                "detail": "reachability is not tested by --health; no network request is made",
            }
        )
    for name in sorted(UNSUPPORTED_SUB_SOURCES):
        entries.append(
            {
                "source": name,
                "kind": "dropped",
                "usable": False,
                "endpoint": None,
                "credential_env": None,
                "credential_configured": None,
                "detail": UNSUPPORTED_SUB_SOURCES[name],
            }
        )
    return {
        "health": "ok",
        "network_used": False,
        "sub_sources": entries,
        "dropped_sub_sources": sorted(UNSUPPORTED_SUB_SOURCES),
    }


def main() -> int:
    if sys.argv[1:] == ["--health"]:
        # stdout must stay exactly "ok" (the Docker integration case asserts
        # stdout.strip() == "ok"), so the inventory goes to stderr.
        print(json.dumps(_health_inventory(), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        print("ok")
        return 0

    if len(sys.argv) < 3:
        print("usage: runner.py <input_type> <value>", file=sys.stderr)
        print("input_type: crypto_address", file=sys.stderr)
        return 2

    input_type = sys.argv[1]
    value = sys.argv[2]

    valid_types = {"crypto_address"}
    if input_type not in valid_types:
        print(
            "Invalid input_type: " + input_type + ". Must be one of: " + str(sorted(valid_types)),
            file=sys.stderr,
        )
        return 2

    # Every candidate sub-source is reported once per run. The dropped candidate
    # is reported as a documented skip and is never queried.
    results = [
        query_mempool_space(value),
        query_blockstream_esplora(value),
        query_blockchair(value),
        query_etherscan_v2(value),
        query_blockcypher(value),
        query_chainabuse(value),
        query_crypttrace(value),
    ]

    output = {
        "input_type": input_type,
        "input_value": value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": [result.to_dict() for result in results],
    }

    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
