"""Fixture/parser and driver tests for the pgp_keys (WKD) adapter.

The parser test runs on ``tests/fixtures/pgp_keys.json``, a synthetic normalized
document derived from the public sample key in the WKD specification. The driver
self-test also parses that sample offline; no live WKD lookup is made here.
"""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.pgp_keys import PgpKeysAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "pgp_keys.json"
EMAIL = "patrice.lumumba@example.net"
FINGERPRINT = "B21DEAB4F875FB3DA42F1D1D139563682A020D0A"


def _request(value=EMAIL):
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.EMAIL, value=value)
    )


def _load_driver():
    path = ROOT / "docker" / "pgp_keys" / "run_pgp_keys.py"
    spec = importlib.util.spec_from_file_location("pgp_keys_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_pgp_keys_descriptor_scoping():
    adapter = PgpKeysAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "pgp_keys"
    assert "Web Key Directory" in descriptor.license
    assert descriptor.input_types == [SeedType.EMAIL]
    assert descriptor.output_types == [EntityType.TECHNICAL_FINDING]
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.docker_image == "aletheia/pgp-keys:v1"
    assert "webkey-service" in descriptor.upstream
    assert adapter.supports(SeedType.EMAIL) is True
    assert adapter.supports(SeedType.USERNAME) is False


def test_pgp_keys_build_command_and_email_validation(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = PgpKeysAdapter().build_command(_request("  " + EMAIL + "  "), workspace)
    assert command == ["/work/email.txt"]
    assert (workspace / "email.txt").read_text(encoding="utf-8") == EMAIL + "\n"
    for bad in ("not-an-email", "two@@example.org", "name@", "@example.org"):
        with pytest.raises(ValueError):
            PgpKeysAdapter().build_command(_request(bad), workspace)


@parser_test("pgp_keys")
def test_pgp_keys_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = PgpKeysAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert result.status == "succeeded"
    assert _values(result) == [
        f"pgp_keys:{FINGERPRINT}",
        "pgp_keys:run:ok",
    ]
    assert len(result.findings) == 2

    by_value = {finding.value: finding for finding in result.findings}
    run = by_value["pgp_keys:run:ok"]
    assert run.entity_type == EntityType.TECHNICAL_FINDING
    assert run.attributes["email"] == EMAIL
    assert run.attributes["method"] == "advanced"
    assert run.attributes["key_count"] == 1
    assert run.attributes["key_block_sha256"].startswith("ccb92ac8")
    assert run.attributes["errors"] == []
    assert run.provenance.confidence == 0.2

    key = by_value[f"pgp_keys:{FINGERPRINT}"]
    assert key.entity_type == EntityType.TECHNICAL_FINDING
    assert key.attributes["kind"] == "openpgp_primary_key"
    assert key.attributes["key_id"] == "139563682A020D0A"
    assert key.attributes["algorithm_name"] == "EdDSA"
    assert key.attributes["user_ids"] == [EMAIL]
    assert key.attributes["wkd_method"] == "advanced"
    assert key.provenance.confidence == 0.7


def test_pgp_keys_parser_not_found_and_errors():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload.update({"status": "not_found", "keys": [], "errors": ["HTTP 404"]})
    result = PgpKeysAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "succeeded"
    assert _values(result) == ["pgp_keys:run:not_found"]

    payload.update({"status": "error", "errors": ["key block invalid"]})
    result = PgpKeysAdapter().parse(_request(), Path("."), json.dumps(payload), "", 1)
    assert result.status == "partial"
    assert _values(result) == ["pgp_keys:run:error"]

    result = PgpKeysAdapter().parse(_request(), Path("."), "not json", "", 1)
    assert result.status == "partial"
    assert _values(result) == ["pgp_keys:run:error"]


def test_pgp_keys_driver_hash_urls_and_sample_key():
    driver = _load_driver()
    parsed = driver._parse_email("Joe.Doe@Example.ORG")
    assert parsed == {
        "address": "Joe.Doe@example.org",
        "local": "Joe.Doe",
        "domain": "example.org",
    }
    assert driver._wkd_hash("Joe.Doe") == "iy9q119eutrkn8s1mk4r39qejnbu3n5q"
    advanced, direct = driver._urls(parsed)
    assert advanced.startswith("https://openpgpkey.example.org/.well-known/openpgpkey/example.org/hu/")
    assert direct.startswith("https://example.org/.well-known/openpgpkey/hu/")
    assert "?l=Joe.Doe" in advanced and "?l=Joe.Doe" in direct

    keys = driver._parse_keys(driver._SAMPLE_PUBLIC_KEY, EMAIL)
    assert len(keys) == 1
    assert keys[0]["fingerprint"] == FINGERPRINT
    assert keys[0]["key_id"] == "139563682A020D0A"
    assert keys[0]["version"] == 4
    assert keys[0]["algorithm"] == 22
    assert keys[0]["algorithm_name"] == "EdDSA"
    assert keys[0]["created_at"] == "2016-06-22T07:25:17Z"
    assert keys[0]["user_ids"] == [EMAIL]
    assert keys[0]["other_uid_count"] == 0

    assert driver._parse_keys(driver._SAMPLE_PUBLIC_KEY, "other@example.net") == []


def test_pgp_keys_driver_normalisation_bounds_and_invalid():
    driver = _load_driver()
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    normalized = driver._normalise(raw)
    assert normalized["status"] == "ok"
    assert normalized["email"] == EMAIL
    assert normalized["method"] == "advanced"
    assert len(normalized["keys"]) == 1
    assert normalized["keys"][0]["fingerprint"] == FINGERPRINT
    assert normalized["keys"][0]["user_ids"] == [EMAIL]

    raw["keys"] = raw["keys"] * 20
    raw["errors"] = ["x"] * 20
    bounded = driver._normalise(raw)
    assert len(bounded["keys"]) == 1
    assert len(bounded["errors"]) == driver.MAX_ERRORS

    raw["keys"] = [{"fingerprint": "not-a-fingerprint", "user_ids": [EMAIL]}]
    raw["status"] = "ok"
    assert driver._normalise(raw)["status"] == "error"

    for bad in ({}, {"source": "other", "email": EMAIL},
                {"source": "pgp_keys", "email": ""}):
        with pytest.raises(ValueError):
            driver._normalise(bad)


def test_pgp_keys_driver_email_file_and_args(tmp_path):
    driver = _load_driver()
    good = tmp_path / "email.txt"
    good.write_text("  " + EMAIL + " \n", encoding="utf-8")
    assert driver._parse_email(good.read_text(encoding="utf-8").strip())["address"] == EMAIL

    for bad in ("not-an-email", "a@b", "x@example.org\nsecond@example.org"):
        with pytest.raises(ValueError):
            driver._parse_email(bad)

    assert driver._parse_args(["--health"]).health is True
    assert driver._parse_args(["--selftest"]).selftest is True
    parsed = driver._parse_args(["--normalize", "combined.json"])
    assert parsed.normalize == "combined.json"
    assert parsed.email_file is None
    assert driver._parse_args(["email.txt"]).email_file == "email.txt"
