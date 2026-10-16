"""Fixture/parser and documented request-contract tests for the transport asset batch."""

import csv
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.adapters.transport_asset_registry import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    TransportAssetFinding,
    TransportAssetRegistryAdapter,
)
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "transport_asset_registry.json"


def _request(seed_type: SeedType = SeedType.NAME, value: str = "N123AB") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=seed_type, value=value),
        legal_only=True,
        authorization_assertion="Synthetic fixture parser test.",
    )


def _load_runner():
    path = ROOT / "docker" / "transport_asset_registry" / "runner.py"
    spec = importlib.util.spec_from_file_location("transport_asset_registry_runner_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@parser_test("transport_asset_registry")
def test_parse_synthetic_fixture_covers_supported_and_dropped_sources():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    result = TransportAssetRegistryAdapter().parse(_request(), Path("."), json.dumps(fixture), "", 0)

    assert result.status == "succeeded"
    assert {finding.attributes["source"] for finding in result.findings} == (
        set(SUPPORTED_SUB_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    )
    assert len(result.findings) == 6
    assert all(isinstance(finding, TransportAssetFinding) for finding in result.findings)
    assert all(finding.entity_type == EntityType.TRANSPORT_ASSET_RECORD for finding in result.findings)
    assert all(finding.provenance.source_url.startswith("https://") for finding in result.findings)
    faa = next(f for f in result.findings if f.attributes["source"] == "faa-aircraft-registration")
    assert faa.registration == "N123AB"
    assert faa.attributes["raw_evidence"]["serial_number"] == "SYNTHETIC-001"
    assert "registrant" not in json.dumps(faa.attributes).lower()
    planespotters = next(f for f in result.findings if f.attributes["source"] == "planespotters")
    assert planespotters.attributes["record_type"] == "aircraft_photo_reference"
    assert "thumbnail" not in json.dumps(planespotters.attributes).lower()


def test_adapter_wiring_and_supported_seed_types():
    adapter = TransportAssetRegistryAdapter()
    assert adapter.supports(SeedType.NAME)
    assert not adapter.supports(SeedType.EMAIL)
    assert adapter.build_command(_request(), Path(".")) == ["name", "N123AB"]

    from aletheia.adapters.registry import phase7_adapters

    assert phase7_adapters()["transport_asset_registry"].descriptor is adapter.descriptor


def test_runner_uses_documented_source_inventory_and_offline_health(monkeypatch, capsys):
    runner = _load_runner()
    monkeypatch.setattr(runner.sys, "argv", ["runner.py", "--health"])
    monkeypatch.setattr(runner, "_request_json", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("health must be offline")))
    monkeypatch.setattr(runner, "_request_bytes", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("health must be offline")))

    assert runner.main() == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "ok"
    health = json.loads(captured.err)
    assert health["network_used"] is False
    assert {entry["source"] for entry in health["sub_sources"]} == set(SUPPORTED_SUB_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)


def _synthetic_faa_zip(registration="N123AB"):
    fields = [""] * 35
    fields[0] = registration
    fields[1] = "SYNTHETIC-001"
    fields[2] = "SYNTH01"
    fields[4] = "2020"
    fields[6] = "Synthetic Private Registrant"
    fields[7] = "123 Synthetic Street"
    fields[19] = "4"
    fields[20] = "1"
    fields[21] = "V"
    fields[22] = "A1B2C3D4"
    fields[34] = "A1B2C3D4"
    csv_bytes = io.StringIO()
    csv.writer(csv_bytes, lineterminator="\n").writerow(fields)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("MASTER.txt", csv_bytes.getvalue())
    return output.getvalue()


def test_faa_lookup_uses_exact_n_number_and_discards_registrant_fields(monkeypatch):
    runner = _load_runner()
    captured = {}

    def fake_request_bytes(url, *, timeout, max_bytes, accept):
        captured.update(url=url, timeout=timeout, max_bytes=max_bytes, accept=accept)
        return _synthetic_faa_zip(), 200, None

    monkeypatch.setattr(runner, "_request_bytes", fake_request_bytes)
    result = runner.query_faa("n123ab")

    assert result.error is None
    assert captured["url"] == runner.FAA_ARCHIVE_URL
    assert captured["max_bytes"] == runner.MAX_FAA_ARCHIVE_BYTES
    record = result.data["records"][0]
    assert record["registration"] == "N123AB"
    assert record["serial_number"] == "SYNTHETIC-001"
    assert record["year_manufactured"] == "2020"
    assert "Synthetic Private Registrant" not in json.dumps(result.to_dict())
    assert "Synthetic Street" not in json.dumps(result.to_dict())


def test_faa_skips_non_n_number_without_network(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "_request_bytes", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fetch for non-N-number")))
    result = runner.query_faa("Central Station")
    assert result.skipped
    assert result.skip_reason


def test_planespotters_uses_keyless_exact_registration_and_omits_images(monkeypatch):
    runner = _load_runner()
    captured = {}

    def fake_request_json(url, *, timeout=15):
        captured["url"] = url
        return {"photos": [{"id": "photo-1", "link": "https://www.planespotters.net/airframe/synthetic", "photographer": "Synthetic Photographer", "thumbnail": {"src": "https://img.invalid/x.jpg"}}]}, 200, None

    monkeypatch.setattr(runner, "_request_json", fake_request_json)
    result = runner.query_planespotters("N123AB")

    assert result.error is None
    assert captured["url"] == runner.PLANESPOTTERS_BASE + "/reg/N123AB"
    assert result.data["records"][0]["source_page"].startswith("https://www.planespotters.net/")
    assert "img.invalid" not in json.dumps(result.to_dict())


def test_openrailwaymap_uses_one_documented_json_request(monkeypatch):
    runner = _load_runner()
    captured = {}

    def fake_request_json(url, *, timeout=15):
        captured.update(url=url, timeout=timeout)
        return [{"osm_id": 123, "name": "Synthetic Station", "railway": "station", "uic_ref": "8000191", "latitude": 48.0, "longitude": 8.0, "operator": "Synthetic Operator"}], 200, None

    monkeypatch.setattr(runner, "_request_json", fake_request_json)
    result = runner.query_openrailwaymap("uic:8000191")

    assert result.error is None
    parsed = urlparse(captured["url"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "api.openrailwaymap.org"
    assert parse_qs(parsed.query) == {"uic_ref": ["8000191"], "limit": ["5"]}
    assert captured["timeout"] == runner.OPENRAILWAYMAP_TIMEOUT_SECONDS
    assert result.data["records"][0]["source_fields"]["osm_id"] == 123


def test_dropped_sources_are_auditable_and_never_queried(monkeypatch, capsys):
    runner = _load_runner()
    monkeypatch.setattr(runner.sys, "argv", ["runner.py", "name", "Central Station"])
    monkeypatch.setattr(runner, "query_faa", lambda value: runner._skip("faa-aircraft-registration", "test"))
    monkeypatch.setattr(runner, "query_openrailwaymap", lambda value: runner._skip("openrailwaymap", "test"))
    monkeypatch.setattr(runner, "query_planespotters", lambda value: runner._skip("planespotters", "test"))

    assert runner.main() == 0
    output = json.loads(capsys.readouterr().out)
    dropped = {source["source"]: source for source in output["sources"] if source["source"] in UNSUPPORTED_SUB_SOURCES}
    assert set(dropped) == set(UNSUPPORTED_SUB_SOURCES)
    assert all(dropped[name]["skipped"] and dropped[name]["data"] is None for name in dropped)
    assert all(dropped[name]["skip_reason"] == UNSUPPORTED_SUB_SOURCES[name] for name in dropped)
