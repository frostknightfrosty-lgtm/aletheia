"""Fixture/parser and driver tests for the crypttrace adapter.

The parser test runs on ``tests/fixtures/crypttrace.json`` — a synthetic
normalized report in the exact shape ``docker/crypttrace/run_crypttrace.py``
emits. Driver checks import the driver file directly; the upstream package is
not installed locally, so only pure helpers and the offline ``--normalize``
image case exercise the container path.
"""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.crypttrace import CrypttraceAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "crypttrace.json"
ADDRESS = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"


def _request(value=ADDRESS):
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.CRYPTO_ADDRESS, value=value)
    )


def _load_driver():
    path = ROOT / "docker" / "crypttrace" / "run_crypttrace.py"
    spec = importlib.util.spec_from_file_location("crypttrace_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_crypttrace_descriptor_scoping():
    adapter = CrypttraceAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "crypttrace"
    assert descriptor.license == "MIT"
    assert descriptor.input_types == [SeedType.CRYPTO_ADDRESS]
    assert descriptor.output_types == [EntityType.BLOCKCHAIN_INTEL_RECORD]
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.docker_image == "aletheia/crypttrace:v1"
    assert descriptor.upstream == "https://github.com/bobslayerX/crypttrace"
    assert "cf60a88b8be43581186965d160114fdaf3022c62" in descriptor.version_pin
    assert adapter.supports(SeedType.CRYPTO_ADDRESS) is True
    assert adapter.supports(SeedType.FILE_PATH) is False


def test_crypttrace_build_command_writes_one_address(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = CrypttraceAdapter().build_command(_request(), workspace)
    assert command == ["/work/address.txt"]
    assert (workspace / "address.txt").read_text(encoding="utf-8") == ADDRESS + "\n"

    for bad in ("", "two\nlines", "x" * 129):
        with pytest.raises(ValueError):
            CrypttraceAdapter().build_command(_request(bad), workspace)


@parser_test("crypttrace")
def test_crypttrace_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = CrypttraceAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert result.status == "succeeded"
    assert _values(result) == [
        "crypttrace:counterparty:3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
        "crypttrace:counterparty:bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
        "crypttrace:entity:1BoatSLRHtKNngkdXEeobR76b53LETtpyT",
        "crypttrace:entity:bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
        "crypttrace:run:ok",
    ]
    assert len(result.findings) == 5
    assert all(f.entity_type == EntityType.BLOCKCHAIN_INTEL_RECORD for f in result.findings)

    by_value = {finding.value: finding for finding in result.findings}
    run = by_value["crypttrace:run:ok"]
    assert run.attributes["subject"] == ADDRESS
    assert run.attributes["summary"]["balance_native"] == 0.125
    assert run.attributes["summary"]["transfers_analysed"] == 4
    assert run.attributes["assessment"]["risk"] == 0
    assert run.attributes["errors"] == []
    assert run.provenance.confidence == 0.3

    entity = by_value[f"crypttrace:entity:{ADDRESS}"]
    assert entity.attributes["rank"] == 1
    assert entity.attributes["label"] == "Example exchange"
    assert entity.attributes["type"] == "exchange"
    assert entity.attributes["risk"] == 70.0
    assert entity.attributes["value_reached"] == 0.01
    assert entity.attributes["usd_reached"] == 1000.0
    assert entity.provenance.confidence == 0.4

    cp = by_value["crypttrace:counterparty:3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"]
    assert cp.attributes["in"] == 0.002
    assert cp.attributes["txs"] == 2.0
    assert cp.provenance.confidence == 0.3


def test_crypttrace_parser_invalid_target_document():
    stdout = json.dumps(
        {"source": "crypttrace", "status": "invalid_target", "error": "bad checksum"}
    )
    result = CrypttraceAdapter().parse(_request(), Path("."), stdout, "", 2)
    assert _values(result) == ["crypttrace:run:invalid_target"]
    assert result.status == "partial"
    assert result.findings[0].attributes["errors"] == []


def test_crypttrace_parser_partial_report_keeps_findings_and_errors():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["status"] = "partial"
    payload["errors"] = ["history: mempool.space request failed: HTTP 429"]
    result = CrypttraceAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "partial"
    assert len(result.findings) == 5
    assert result.findings[0].attributes["errors"] == [
        "history: mempool.space request failed: HTTP 429"
    ]


def test_crypttrace_parser_malformed_output_never_crashes():
    result = CrypttraceAdapter().parse(_request(), Path("."), "not json", "", 1)
    assert _values(result) == ["crypttrace:run:error"]
    assert result.status == "partial"
    assert len(result.findings) == 1


def test_crypttrace_driver_normalises_and_bounds():
    driver = _load_driver()
    normalised = driver._normalise(driver._SAMPLE_REPORT)
    assert normalised["source"] == "crypttrace"
    assert normalised["status"] == "ok"
    assert normalised["subject"] == driver._SAMPLE_REPORT["subject"]
    assert len(normalised["key_findings"]) == 1
    assert len(normalised["top_counterparties"]) == 1
    assert "tree_text" not in normalised

    with pytest.raises(ValueError):
        driver._normalise({})
    with pytest.raises(ValueError):
        driver._normalise({**driver._SAMPLE_REPORT, "chain": "eth"})
    with pytest.raises(ValueError):
        driver._normalise([])


def test_crypttrace_driver_address_file_and_args(tmp_path):
    driver = _load_driver()
    good = tmp_path / "address.txt"
    good.write_text(ADDRESS + "\n", encoding="utf-8")
    assert driver._read_address(good) == ADDRESS

    both = tmp_path / "both.txt"
    both.write_text(ADDRESS + "\n" + ADDRESS + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        driver._read_address(both)

    missing = tmp_path / "missing.txt"
    with pytest.raises(ValueError):
        driver._read_address(missing)

    assert driver._parse_args(["--health"]).health is True
    assert driver._parse_args(["--selftest"]).selftest is True
    parsed = driver._parse_args(["--normalize", "report.json"])
    assert parsed.normalize == "report.json"
    assert parsed.address_file is None
    assert driver._parse_args(["address.txt"]).address_file == "address.txt"
