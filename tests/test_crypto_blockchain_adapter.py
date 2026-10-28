"""Parser + fixture tests for the crypto_blockchain batch adapter."""

import hashlib
import importlib.util
import inspect
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.core.models import (
    AdapterRunRequest,
    EntityType,
    Provenance,
    Seed,
    SeedType,
)

from aletheia.adapters.crypto_blockchain import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    CryptoBlockchainAdapter,
    CryptoBlockchainFinding,
    _extract_address_family,
    _extract_chain,
    _extract_details,
    _extract_record_type,
    _extract_subject,
)


# -- fixture -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FIXTURE_PATH = "tests/fixtures/crypto_blockchain.json"
FIXTURE_PATH = ROOT / EXPECTED_FIXTURE_PATH

SUPPORTED_SOURCES = (
    "mempool-space",
    "blockstream-esplora",
    "blockchair",
    "etherscan-v2",
    "blockcypher",
    "chainabuse",
)

FIXTURE_INPUT_VALUE = "1SyntheticCryptoAddrForFixture"

# The documented address endpoint constant each implemented sub-source resolves
# its URL from, plus the documentation constant, so the fixture can never point
# at an endpoint the runner does not use.
URL_CONSTANTS = {
    "mempool-space": "MEMPOOL_SPACE_ADDRESS_URL",
    "blockstream-esplora": "BLOCKSTREAM_ESPLORA_ADDRESS_URL",
    "blockchair": "BLOCKCHAIR_BITCOIN_ADDRESS_URL",
    "blockcypher": "BLOCKCYPHER_BITCOIN_ADDRESS_URL",
}

DOC_CONSTANTS = {
    "mempool-space": "MEMPOOL_SPACE_DOCS",
    "blockstream-esplora": "BLOCKSTREAM_ESPLORA_DOCS",
    "blockchair": "BLOCKCHAIR_DOCS",
    "blockcypher": "BLOCKCYPHER_DOCS",
}


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "crypto_blockchain_runner",
        ROOT / "docker" / "crypto_blockchain" / "runner.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runner_function(module, source: str):
    return getattr(module, "query_" + source.replace("-", "_"))


# -- subject extraction --------------------------------------------------------


def test_extract_subject_mempool_space():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "summary"}]}
    assert _extract_subject(data, "mempool-space") == "MEMPOOL:" + FIXTURE_INPUT_VALUE


def test_extract_subject_blockstream_esplora():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "summary"}]}
    assert _extract_subject(data, "blockstream-esplora") == "ESPLORA:" + FIXTURE_INPUT_VALUE


def test_extract_subject_blockchair():
    data = {"records": [{"record_id": FIXTURE_INPUT_VALUE, "detail": "dashboard"}]}
    assert _extract_subject(data, "blockchair") == "BLOCKCHAIR:" + FIXTURE_INPUT_VALUE


def test_extract_subject_etherscan_v2():
    data = {"records": [{"record_id": "0xabc123", "detail": "tx"}]}
    assert _extract_subject(data, "etherscan-v2") == "ETHERSCAN:0xabc123"


def test_extract_subject_chainabuse():
    data = {"records": [{"record_id": "52907745-7672-470e-a803-a2f8feb52944", "detail": "report"}]}
    assert (
        _extract_subject(data, "chainabuse")
        == "CHAINABUSE:52907745-7672-470e-a803-a2f8feb52944"
    )


def test_extract_subject_without_a_record_falls_back_to_source():
    """A payload with no record never claims a record subject."""
    for source in SUPPORTED_SOURCES:
        assert _extract_subject({"records": [], "record_count": 0}, source) == source


# -- record type, address family and chain extraction --------------------------


def test_extract_record_type():
    cases = [
        ("mempool-space", "mempool_space_bitcoin_address"),
        ("blockstream-esplora", "esplora_bitcoin_address"),
        ("blockchair", "blockchair_address_dashboard"),
        ("etherscan-v2", "etherscan_ethereum_transaction"),
        ("blockcypher", "blockcypher_address"),
        ("chainabuse", "chainabuse_scam_report"),
        ("crypttrace", None),
        ("unknown-source", None),
    ]
    for source, expected in cases:
        record = None if source in ("crypttrace", "unknown-source") else {"record_id": "x"}
        data = {"records": [record] if record else []}
        result = _extract_record_type(data, source)
        assert result == expected, f"{source}: expected {expected}, got {result}"


def test_extract_address_family():
    assert _extract_address_family({"address_family": "bitcoin"}, "mempool-space") == "bitcoin"
    assert _extract_address_family({"address_family": "ethereum"}, "etherscan-v2") == "ethereum"
    assert _extract_address_family({}, "mempool-space") is None


def test_extract_chain():
    assert _extract_chain({"chain": "bitcoin"}, "blockchair") == "bitcoin"
    assert _extract_chain({"coin": "btc", "network": "main"}, "blockcypher") == "bitcoin"
    assert _extract_chain({"coin": "eth", "network": "main"}, "blockcypher") == "ethereum"
    assert _extract_chain({}, "mempool-space") == "bitcoin"
    assert _extract_chain({}, "blockstream-esplora") == "bitcoin"
    assert _extract_chain({}, "etherscan-v2") == "ethereum"
    assert _extract_chain({}, "chainabuse") is None


# -- details extraction --------------------------------------------------------


def test_extract_details_mempool_space():
    data = {
        "api_source": "mempool.space REST API (Bitcoin)",
        "api_documentation": "https://mempool.space/docs/api/rest",
        "address_family": "bitcoin",
        "endpoint": "https://mempool.space/api/address/" + FIXTURE_INPUT_VALUE,
        "record_count": 1,
        "truncated": False,
        "records": [
            {
                "record_id": FIXTURE_INPUT_VALUE,
                "detail": "summary",
                "chain_tx_count": 7,
                "chain_funded_txo_sum": 15007599040,
                "chain_spent_txo_sum": 15007599040,
            }
        ],
    }
    result = _extract_details(data, "mempool-space")
    assert result["chain_tx_count"] == 7
    assert result["chain_funded_txo_sum"] == 15007599040
    assert result["record_count"] == 1
    assert result["truncated"] is False


def test_extract_details_blockchair():
    data = {
        "api_source": "Blockchair API (bitcoin address dashboard)",
        "chain": "bitcoin",
        "context_code": 200,
        "address_family": "bitcoin",
        "records": [
            {
                "record_id": FIXTURE_INPUT_VALUE,
                "detail": "dashboard",
                "balance": 0,
                "transaction_count": 7,
                "received": 15007599040,
                "spent": 15007599040,
            }
        ],
    }
    result = _extract_details(data, "blockchair")
    assert result["chain"] == "bitcoin"
    assert result["transaction_count"] == 7
    assert result["context_code"] == 200


def test_extract_details_etherscan_v2():
    data = {
        "api_source": "Etherscan API V2 (account/txlist, chainid=1)",
        "address_family": "ethereum",
        "records": [
            {
                "record_id": "0xabc123",
                "detail": "tx",
                "block_number": "23467053",
                "hash": "0xabc123",
                "from": "0xfrom",
                "to": "0xto",
                "value": "0",
                "is_error": "0",
            }
        ],
    }
    result = _extract_details(data, "etherscan-v2")
    assert result["hash"] == "0xabc123"
    assert result["from"] == "0xfrom"
    assert result["block_number"] == "23467053"


def test_extract_details_chainabuse():
    data = {
        "api_source": "Chainabuse Public API (v1.2 Get Reports)",
        "count": 1,
        "records": [
            {
                "record_id": "52907745-7672-470e-a803-a2f8feb52944",
                "detail": "report",
                "scam_category": "RUG_PULL",
                "trusted": True,
                "checked": True,
            }
        ],
    }
    result = _extract_details(data, "chainabuse")
    assert result["scam_category"] == "RUG_PULL"
    assert result["trusted"] is True
    assert result["count"] == 1


def test_extract_details_without_a_record_is_none():
    assert _extract_details({"records": []}, "mempool-space") is None


# -- finding schema ------------------------------------------------------------


def test_finding_can_construct():
    finding = CryptoBlockchainFinding(
        subject="MEMPOOL:" + FIXTURE_INPUT_VALUE,
        source="mempool-space",
        record_type="mempool_space_bitcoin_address",
        address=FIXTURE_INPUT_VALUE,
        address_family="bitcoin",
        chain="bitcoin",
        identifier=FIXTURE_INPUT_VALUE,
        date="2026-10-16",
        details={"chain_tx_count": 7},
        raw_evidence={"records": [{"record_id": FIXTURE_INPUT_VALUE}]},
        raw_hash="abc123",
        provenance=Provenance(
            tool="test",
            source_url="sub-source:mempool-space",
            confidence=0.80,
            raw_evidence_sha256="hash123",
            adapter_version="1.0",
            notes=["Normalized from mempool-space"],
        ),
    )
    assert finding.entity_type == EntityType.BLOCKCHAIN_INTEL_RECORD
    assert finding.entity_type.value == "blockchain_intel_record"
    assert finding.attributes["source"] == "mempool-space"
    assert finding.attributes["chain"] == "bitcoin"
    assert finding.subject == "MEMPOOL:" + FIXTURE_INPUT_VALUE
    assert finding.address == FIXTURE_INPUT_VALUE


def test_fixture_covers_every_sub_source_once():
    fixture = load_fixture()
    runner = _load_runner()
    sources = [s["source"] for s in fixture["sources"]]
    assert len(sources) == 7
    assert set(sources) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    assert tuple(runner.SUPPORTED_SUB_SOURCES) == tuple(SUPPORTED_SOURCES)
    assert runner.UNSUPPORTED_SUB_SOURCES == UNSUPPORTED_SUB_SOURCES

    by_source = {s["source"]: s for s in fixture["sources"]}
    for source in SUPPORTED_SOURCES:
        if source in ("etherscan-v2", "chainabuse"):
            # The two key-required sub-sources are recorded as documented skips
            # when their environment variable is unset.
            assert by_source[source]["skipped"] is True, source
            continue
        entry = by_source[source]
        assert entry["skipped"] is False, source
        assert entry["error"] is None, source
        assert entry["http_status"] == 200, source
        assert entry["data"], source
        # The fixture hash uses the same convention as the runner: sha256 over
        # json.dumps(data, sort_keys=True).
        assert entry["raw_hash"] == hashlib.sha256(
            json.dumps(entry["data"], sort_keys=True).encode()
        ).hexdigest(), source
        # The recorded artefact URL is the one the runner actually requests, so a
        # fixture can never point at an endpoint the runner does not use.
        assert entry["data"]["endpoint"] == getattr(runner, URL_CONSTANTS[source]).format(
            address=FIXTURE_INPUT_VALUE
        ), source
        assert entry["data"]["api_documentation"] == getattr(runner, DOC_CONSTANTS[source]), source
        assert entry["data"]["query"] == FIXTURE_INPUT_VALUE, source


def test_fixture_dropped_candidate_is_skipped_with_its_exact_reason(monkeypatch):
    """The dropped candidate is an auditable skip, never a fabricated call."""
    fixture = load_fixture()
    runner = _load_runner()
    by_source = {s["source"]: s for s in fixture["sources"]}
    for name, reason in UNSUPPORTED_SUB_SOURCES.items():
        entry = by_source[name]
        assert entry["skipped"] is True, name
        assert entry["skip_reason"] == reason, name
        assert entry["raw_hash"] is None, name
        assert entry["data"] is None, name
    assert by_source["crypttrace"]["skip_reason"] == runner.UNSUPPORTED_SUB_SOURCES["crypttrace"]

    # The recorded key-required skip reasons are exactly what the runner produces.
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    monkeypatch.delenv("CHAINABUSE_API_KEY", raising=False)
    assert by_source["etherscan-v2"]["skip_reason"] == runner.query_etherscan_v2(
        FIXTURE_INPUT_VALUE
    ).skip_reason
    assert by_source["chainabuse"]["skip_reason"] == runner.query_chainabuse(
        FIXTURE_INPUT_VALUE
    ).skip_reason


def test_fixture_uses_only_synthetic_values():
    """The fixture is synthetic and must not read as captured live output."""
    fixture = load_fixture()
    assert "Synthetic" in fixture["input_value"]
    for entry in fixture["sources"]:
        if not entry["data"]:
            continue
        assert entry["data"]["query"] == fixture["input_value"]


# -- run result parsing --------------------------------------------------------


def _request(value: str = FIXTURE_INPUT_VALUE) -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.CRYPTO_ADDRESS, value=value), legal_only=True
    )


def _source(source: str, **overrides) -> dict:
    entry = {
        "source": source,
        "skipped": False,
        "skip_reason": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "http_status": 200,
        "error": None,
        "raw_hash": None,
        "data": None,
    }
    entry.update(overrides)
    return entry


def _payload(sources: list[dict]) -> str:
    return json.dumps(
        {
            "input_type": "crypto_address",
            "input_value": FIXTURE_INPUT_VALUE,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
        }
    )


def _assert_provenance_hash_invariant(findings) -> None:
    for finding in findings:
        raw = finding.attributes.get("raw_evidence")
        assert raw, finding.attributes["source"]
        assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
            json.dumps(raw, sort_keys=True).encode()
        ).hexdigest(), finding.attributes["source"]


@parser_test("crypto_blockchain")
def test_parse_success():
    fixture = load_fixture()
    json_stdout = json.dumps(fixture)

    adapter = CryptoBlockchainAdapter()
    result = adapter.parse(_request(), Path("."), json_stdout, "", 0)

    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == len(fixture["sources"]) == 7

    by_source = {f.attributes["source"]: f for f in result.findings}
    assert set(by_source) == set(SUPPORTED_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)

    mempool = by_source["mempool-space"]
    assert mempool.value == "MEMPOOL:" + FIXTURE_INPUT_VALUE
    assert mempool.subject == "MEMPOOL:" + FIXTURE_INPUT_VALUE
    assert mempool.record_type == "mempool_space_bitcoin_address"
    assert mempool.address == FIXTURE_INPUT_VALUE
    assert mempool.address_family == "bitcoin"
    assert mempool.chain == "bitcoin"
    assert mempool.attributes["details"]["chain_tx_count"] == 7
    assert mempool.attributes["date"] == fixture["sources"][0]["timestamp"][:10]

    esplora = by_source["blockstream-esplora"]
    assert esplora.value == "ESPLORA:" + FIXTURE_INPUT_VALUE
    assert esplora.record_type == "esplora_bitcoin_address"
    assert esplora.chain == "bitcoin"

    blockchair = by_source["blockchair"]
    assert blockchair.value == "BLOCKCHAIR:" + FIXTURE_INPUT_VALUE
    assert blockchair.record_type == "blockchair_address_dashboard"
    assert blockchair.chain == "bitcoin"
    assert blockchair.attributes["details"]["transaction_count"] == 7
    assert blockchair.attributes["details"]["received"] == 15007599040

    blockcypher = by_source["blockcypher"]
    assert blockcypher.value == "BLOCKCYPHER:" + FIXTURE_INPUT_VALUE
    assert blockcypher.record_type == "blockcypher_address"
    assert blockcypher.attributes["details"]["coin"] == "btc"
    assert blockcypher.attributes["details"]["n_tx"] == 7

    etherscan = by_source["etherscan-v2"]
    assert etherscan.value == "etherscan-v2:skipped"
    assert etherscan.record_type is None
    assert etherscan.attributes["details"]["skipped"] is True
    assert "ETHERSCAN_API_KEY is not set" in etherscan.attributes["details"]["reason"]

    chainabuse = by_source["chainabuse"]
    assert chainabuse.value == "chainabuse:skipped"
    assert chainabuse.record_type is None
    assert "CHAINABUSE_API_KEY is not set" in chainabuse.provenance.notes[0]

    crypttrace = by_source["crypttrace"]
    assert crypttrace.value == "crypttrace:skipped"
    assert crypttrace.record_type is None
    assert crypttrace.attributes["details"] == {
        "skipped": True,
        "reason": UNSUPPORTED_SUB_SOURCES["crypttrace"],
    }

    for finding in result.findings:
        assert isinstance(finding, CryptoBlockchainFinding)
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.BLOCKCHAIN_INTEL_RECORD)
        assert finding.provenance.tool == "crypto_blockchain"
        assert finding.provenance.source_url == f"sub-source:{finding.attributes['source']}"
        assert finding.provenance.confidence == 0.80

    _assert_provenance_hash_invariant(result.findings)

    # A mixed runner payload must yield a real finding, a skip finding and an
    # error finding, each with the same provenance hash invariant.
    mixed = _payload(
        [
            _source(
                "blockstream-esplora",
                data=fixture["sources"][1]["data"],
                raw_hash=fixture["sources"][1]["raw_hash"],
            ),
            _source(
                "etherscan-v2",
                skipped=True,
                skip_reason="ETHERSCAN_API_KEY is not set for this run",
                http_status=0,
            ),
            _source(
                "chainabuse",
                http_status=503,
                error="HTTP 503: Service Unavailable",
            ),
        ]
    )
    mixed_result = adapter.parse(_request(), Path("."), mixed, "", 0)

    assert mixed_result.status == "succeeded"
    assert len(mixed_result.findings) == 3
    mixed_by_source = {f.attributes["source"]: f for f in mixed_result.findings}

    ok_finding = mixed_by_source["blockstream-esplora"]
    assert ok_finding.value == "ESPLORA:" + FIXTURE_INPUT_VALUE
    assert ok_finding.record_type == "esplora_bitcoin_address"

    skipped_finding = mixed_by_source["etherscan-v2"]
    assert skipped_finding.value == "etherscan-v2:skipped"
    assert skipped_finding.record_type is None
    assert skipped_finding.attributes["details"] == {
        "skipped": True,
        "reason": "ETHERSCAN_API_KEY is not set for this run",
    }
    assert "Skipped: ETHERSCAN_API_KEY is not set for this run" in skipped_finding.provenance.notes

    error_finding = mixed_by_source["chainabuse"]
    assert error_finding.value == "chainabuse:error"
    assert error_finding.record_type is None
    assert error_finding.attributes["details"] == {
        "error": "HTTP 503: Service Unavailable",
        "http_status": 503,
    }
    assert "Error: HTTP 503: Service Unavailable" in error_finding.provenance.notes

    for finding in mixed_result.findings:
        assert finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.BLOCKCHAIN_INTEL_RECORD)
    _assert_provenance_hash_invariant(mixed_result.findings)


def test_parse_skipped():
    """A skipped sub-source produces a finding that carries the skip reason."""
    reason = "CHAINABUSE_API_KEY is not set for this run"
    payload = _payload([_source("chainabuse", skipped=True, skip_reason=reason, http_status=0)])

    adapter = CryptoBlockchainAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "chainabuse"
    assert finding.value == "chainabuse:skipped"
    assert finding.record_type is None
    assert finding.attributes["details"] == {"skipped": True, "reason": reason}
    assert finding.attributes["raw_evidence"] == {"skipped": True, "reason": reason}
    assert f"Skipped: {reason}" in finding.provenance.notes


def test_parse_error():
    """An errored sub-source produces an error finding, not a record."""
    payload = _payload(
        [_source("mempool-space", http_status=429, error="HTTP 429: Too Many Requests")]
    )

    adapter = CryptoBlockchainAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.attributes["source"] == "mempool-space"
    assert finding.value == "mempool-space:error"
    assert finding.attributes["details"] == {
        "error": "HTTP 429: Too Many Requests",
        "http_status": 429,
    }
    assert "Error: HTTP 429: Too Many Requests" in finding.provenance.notes

    # A sub-source error must not be reported as a successful record.
    assert finding.record_type is None
    assert finding.attributes.get("raw_evidence") == {
        "error": "HTTP 429: Too Many Requests",
        "http_status": 429,
    }
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(
        json.dumps(finding.attributes["raw_evidence"], sort_keys=True).encode()
    ).hexdigest()


def test_parse_no_match_produces_no_finding():
    """A source with no record must not be reported as a finding."""
    payload = _payload([_source("blockchair", data=None, raw_hash=None)])

    adapter = CryptoBlockchainAdapter()
    result = adapter.parse(_request(), Path("."), payload, "", 0)

    assert result.status == "succeeded"
    assert result.findings == []


def test_parse_non_json_stdout_is_partial():
    """Non-JSON runner output must not be treated as a successful parse."""
    adapter = CryptoBlockchainAdapter()
    result = adapter.parse(_request(), Path("."), "not json at all", "", 0)

    assert result.status == "partial"
    assert result.findings == []
    assert "not valid JSON" in result.stderr_tail


def test_parse_nonzero_exit_is_failed():
    """A non-zero runner exit code must fail the run and produce no findings."""
    adapter = CryptoBlockchainAdapter()
    result = adapter.parse(_request(), Path("."), "", "boom", 1)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.findings == []
    assert "boom" in result.stderr_tail


# -- adapter wiring ------------------------------------------------------------


def test_adapter_supports_types():
    adapter = CryptoBlockchainAdapter()
    assert adapter.supports(SeedType.CRYPTO_ADDRESS)
    assert not adapter.supports(SeedType.NAME)
    assert not adapter.supports(SeedType.EMAIL)
    assert not adapter.supports(SeedType.DOMAIN)


def test_adapter_input_types():
    adapter = CryptoBlockchainAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.CRYPTO_ADDRESS, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    cmd = adapter.build_command(req, None)
    assert cmd[0] == "crypto_address"
    assert adapter.descriptor.input_types == [SeedType.CRYPTO_ADDRESS]


def test_adapter_build_command_crypto_address():
    adapter = CryptoBlockchainAdapter()
    seed_obj = type("Seed", (), {"type": SeedType.CRYPTO_ADDRESS, "value": "test_val"})()
    req = type("Req", (), {"run_id": "test", "seed": seed_obj})()
    assert adapter.build_command(req, None) == ["crypto_address", "test_val"]


def test_adapter_is_registered_and_not_parser_test_exempt():
    from aletheia.adapters.registry import phase7_adapters

    registry = phase7_adapters()
    assert "crypto_blockchain" in registry

    descriptor = registry["crypto_blockchain"].descriptor
    assert descriptor.name == "crypto_blockchain"
    assert descriptor.input_types == [SeedType.CRYPTO_ADDRESS]
    assert descriptor.output_types == [EntityType.BLOCKCHAIN_INTEL_RECORD]
    assert descriptor.docker_image == "aletheia/crypto-blockchain:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == [
        "BLOCKCHAIR_API_KEY",
        "BLOCKCYPHER_API_TOKEN",
        "ETHERSCAN_API_KEY",
        "CHAINABUSE_API_KEY",
    ]
    assert descriptor.parser_test_exempt is False
    assert not getattr(descriptor, "parser_test_exempt", False)
    assert descriptor.upstream.endswith("docker/crypto_blockchain")


# -- docker runner -------------------------------------------------------------


def test_runner_health_check():
    runner = _load_runner()
    old_argv = sys.argv
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.argv = ["runner.py", "--health"]
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        assert runner.main() == 0
        assert sys.stdout.getvalue().strip() == "ok"
        inventory = json.loads(sys.stderr.getvalue().strip())
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    assert inventory["health"] == "ok"
    assert inventory["network_used"] is False
    kinds = {entry["source"]: entry["kind"] for entry in inventory["sub_sources"]}
    assert kinds["mempool-space"] == "http_api"
    assert kinds["chainabuse"] == "http_api"
    assert kinds["crypttrace"] == "dropped"
    assert inventory["dropped_sub_sources"] == ["crypttrace"]


def test_runner_rejects_invalid_arguments():
    runner = _load_runner()
    old_argv = sys.argv
    old_stderr = sys.stderr
    try:
        sys.stderr = io.StringIO()
        sys.argv = ["runner.py"]
        assert runner.main() == 2
        sys.argv = ["runner.py", "invalid_type", FIXTURE_INPUT_VALUE]
        assert runner.main() == 2
    finally:
        sys.argv = old_argv
        sys.stderr = old_stderr


def test_runner_reports_every_sub_source():
    runner = _load_runner()
    assert tuple(runner.SUPPORTED_SUB_SOURCES) == tuple(SUPPORTED_SOURCES)
    for source in SUPPORTED_SOURCES:
        function = _runner_function(runner, source)
        assert callable(function)
    assert callable(runner.query_crypttrace)
    result = runner.SourceResult("example")
    assert set(result.to_dict()) == {
        "source",
        "skipped",
        "skip_reason",
        "timestamp",
        "http_status",
        "error",
        "raw_hash",
        "data",
    }


def test_runner_defines_no_endpoint_for_dropped_source():
    """A dropped candidate is an auditable skip with no URL, never a guessed call."""
    runner = _load_runner()
    for source, reason in runner.UNSUPPORTED_SUB_SOURCES.items():
        assert isinstance(reason, str) and reason.strip()
        function_source = inspect.getsource(_runner_function(runner, source))
        assert "http://" not in function_source
        assert "https://" not in function_source


def test_runner_supported_sources_cite_a_documented_endpoint():
    """Every implemented sub-source queries one documented HTTPS endpoint."""
    runner = _load_runner()
    endpoint_constants = {
        "mempool-space": "MEMPOOL_SPACE_ADDRESS_URL",
        "blockstream-esplora": "BLOCKSTREAM_ESPLORA_ADDRESS_URL",
        "blockchair": "BLOCKCHAIR_BITCOIN_ADDRESS_URL",
        "etherscan-v2": "ETHERSCAN_V2_API_URL",
        "blockcypher": "BLOCKCYPHER_BITCOIN_ADDRESS_URL",
        "chainabuse": "CHAINABUSE_REPORTS_URL",
    }
    for source, constant in endpoint_constants.items():
        endpoint = getattr(runner, constant)
        assert endpoint.startswith("https://"), source
        function_source = inspect.getsource(_runner_function(runner, source))
        assert constant in function_source, source


def test_runner_skips_key_required_sources_without_their_key(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    monkeypatch.delenv("CHAINABUSE_API_KEY", raising=False)

    eth = runner.query_etherscan_v2("0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae")
    assert eth.skipped is True
    assert "ETHERSCAN_API_KEY" in eth.skip_reason

    abuse = runner.query_chainabuse(FIXTURE_INPUT_VALUE)
    assert abuse.skipped is True
    assert "CHAINABUSE_API_KEY" in abuse.skip_reason


def test_runner_skips_a_chain_mismatch(monkeypatch):
    """A Bitcoin address is never sent to the Ethereum-only Etherscan endpoint."""
    runner = _load_runner()
    monkeypatch.setenv("ETHERSCAN_API_KEY", "test-key")
    result = runner.query_etherscan_v2(FIXTURE_INPUT_VALUE)
    assert result.skipped is True
    assert "Ethereum" in result.skip_reason

    # And an Ethereum address is never sent to the Bitcoin-only explorers.
    eth_address = "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae"
    assert runner.query_mempool_space(eth_address).skipped is True
    assert runner.query_blockstream_esplora(eth_address).skipped is True


def test_runner_address_family_classification():
    runner = _load_runner()
    assert runner._address_family(FIXTURE_INPUT_VALUE) == "bitcoin"
    assert runner._address_family("0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae") == "ethereum"
    assert runner._address_family("not-an-address") == "unknown"


def test_runner_parses_the_documented_mempool_space_shape(monkeypatch):
    runner = _load_runner()
    payload = {
        "address": FIXTURE_INPUT_VALUE,
        "chain_stats": {
            "funded_txo_count": 5,
            "funded_txo_sum": 15007599040,
            "spent_txo_count": 5,
            "spent_txo_sum": 15007599040,
            "tx_count": 7,
        },
        "mempool_stats": {"funded_txo_count": 0, "funded_txo_sum": 0, "spent_txo_count": 0, "spent_txo_sum": 0, "tx_count": 0},
    }
    monkeypatch.setattr(runner, "_fetch_json", lambda *a, **k: (payload, 200, None))
    result = runner.query_mempool_space(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert result.http_status == 200
    assert result.data["records"][0]["chain_tx_count"] == 7
    assert result.data["records"][0]["record_id"] == FIXTURE_INPUT_VALUE


def test_runner_parses_the_documented_chainabuse_shape(monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("CHAINABUSE_API_KEY", "ca_test_key")
    payload = {
        "reports": [
            {
                "id": "52907745-7672-470e-a803-a2f8feb52944",
                "trusted": True,
                "checked": True,
                "scamCategory": "RUG_PULL",
                "createdAt": "2022-09-09T04:53:16.591Z",
                "addresses": [{"address": FIXTURE_INPUT_VALUE, "chain": "BTC", "domain": None}],
            }
        ],
        "count": 1,
    }
    monkeypatch.setattr(runner, "_fetch_json", lambda *a, **k: (payload, 200, None))
    result = runner.query_chainabuse(FIXTURE_INPUT_VALUE)

    assert result.error is None
    assert result.data["count"] == 1
    record = result.data["records"][0]
    assert record["scam_category"] == "RUG_PULL"
    assert record["trusted"] is True
    assert record["addresses"][0]["address"] == FIXTURE_INPUT_VALUE


def test_runner_records_an_http_error_without_leaking_the_key(monkeypatch):
    """A failing keyed request is recorded as an error with a redacted endpoint."""
    runner = _load_runner()
    monkeypatch.setenv("ETHERSCAN_API_KEY", "super-secret-key")
    monkeypatch.setattr(
        runner, "_fetch_json", lambda *a, **k: (None, 403, "HTTP 403: Forbidden")
    )
    result = runner.query_etherscan_v2("0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae")
    assert result.error == "HTTP 403: Forbidden"
    assert result.data is None
