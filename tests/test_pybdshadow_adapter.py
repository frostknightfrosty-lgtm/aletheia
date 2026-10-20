"""Fixture/parser and driver tests for the pybdshadow adapter.

The parser test runs on ``tests/fixtures/pybdshadow.json`` — a synthetic
document in the exact shape the pinned driver prints (see
``docker/pybdshadow``). Driver checks import the driver file directly; nothing
here needs the upstream package, network access, or Docker.

The ``@parser_test("pybdshadow")`` marker pins parser coverage for the parser
pre-flight.
"""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.pybdshadow import PybdshadowAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "pybdshadow.json"


def _document(**overrides):
    document = {
        "datetime_utc": "2024-06-01T12:00:00Z",
        "buildings": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"building_id": "b1", "height": 10.0},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [0.0, 0.0], [0.0002, 0.0], [0.0002, 0.0002],
                            [0.0, 0.0002], [0.0, 0.0],
                        ]],
                    },
                }
            ],
        },
    }
    document.update(overrides)
    return document


def _request(value="fixture.json"):
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.FILE_PATH, value=value)
    )


def _load_driver():
    path = ROOT / "docker" / "pybdshadow" / "run_pybdshadow.py"
    spec = importlib.util.spec_from_file_location("pybdshadow_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_pybdshadow_descriptor_scoping():
    adapter = PybdshadowAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "pybdshadow"
    assert descriptor.license == "BSD-3-Clause"
    assert descriptor.input_types == [SeedType.FILE_PATH]
    assert descriptor.output_types == [EntityType.GEO_EVIDENCE]
    assert descriptor.network_required is False
    assert descriptor.requires_authorization_assertion is False
    assert descriptor.docker_image == "aletheia/pybdshadow:v1"
    assert descriptor.upstream == "https://github.com/ni1o1/pybdshadow"
    assert "e2665ee7a6527b9fb0d581bbf7d6dc2914015b02" in descriptor.version_pin
    assert adapter.supports(SeedType.FILE_PATH) is True
    assert adapter.supports(SeedType.SHADOW_OBSERVATION) is False


def test_pybdshadow_build_command_copies_input(tmp_path):
    source = tmp_path / "buildings.json"
    source.write_text(json.dumps(_document()), encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = PybdshadowAdapter().build_command(_request(str(source)), workspace)
    assert command == ["/work/input.json"]
    assert (workspace / "input.json").read_bytes() == source.read_bytes()


def test_pybdshadow_build_command_rejects_bad_inputs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(FileNotFoundError):
        PybdshadowAdapter().build_command(_request(str(tmp_path / "missing.json")), workspace)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * 1_000_000)
    with pytest.raises(ValueError):
        PybdshadowAdapter().build_command(_request(str(oversized)), workspace)


@parser_test("pybdshadow")
def test_pybdshadow_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = PybdshadowAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert json.loads(stdout)["pinned_commit"] in PybdshadowAdapter.descriptor.version_pin
    assert _values(result) == [
        "pybdshadow:run:ok",
        "pybdshadow:shadow:1",
        "pybdshadow:shadow:2",
    ]
    assert len(result.findings) == 3
    assert all(finding.entity_type == EntityType.GEO_EVIDENCE for finding in result.findings)

    by_value = {finding.value: finding for finding in result.findings}
    run = by_value["pybdshadow:run:ok"]
    assert run.attributes["status"] == "ok"
    assert run.attributes["input"] == {
        "datetime_utc": "2024-06-01T12:00:00Z",
        "buildings_total": 2,
    }
    assert run.attributes["thresholds"]["max_buildings"] == 200
    assert run.attributes["shadows_total"] == 2
    assert run.provenance.confidence == 0.3

    first = by_value["pybdshadow:shadow:1"]
    assert first.attributes["rank"] == 1
    assert first.attributes["building_id"] == "b1"
    assert first.attributes["bbox"] == [-0.00012, -0.00004, 0.0002, 0.00021]
    assert first.attributes["centroid"] == [0.00004, 0.00008]
    assert first.attributes["shadow_area_m2"] == 23.457
    assert first.attributes["polygons"] == 1
    assert first.attributes["vertices"] == 5
    assert first.provenance.confidence == 0.4


def test_pybdshadow_parser_invalid_target_document():
    stdout = json.dumps(
        {"source": "pybdshadow", "status": "invalid_target", "error": "bad document"}
    )
    result = PybdshadowAdapter().parse(_request(), Path("."), stdout, "", 2)
    assert _values(result) == ["pybdshadow:run:invalid_target"]
    assert result.status == "partial"
    assert result.findings[0].attributes["reason"] == "bad document"


def test_pybdshadow_parser_no_sunlight_document():
    stdout = json.dumps(
        {"source": "pybdshadow", "status": "no_sunlight", "error": "below the horizon"}
    )
    result = PybdshadowAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert _values(result) == ["pybdshadow:run:no_sunlight"]
    assert result.status == "succeeded"
    assert result.findings[0].attributes["reason"] == "below the horizon"


def test_pybdshadow_parser_ignores_malformed_shadows():
    stdout = json.dumps(
        {
            "source": "pybdshadow",
            "status": "ok",
            "shadows": [
                {"building_id": "b1"},
                {"bbox": [1.0, 2.0, 3.0], "centroid": [0.0, 0.0]},
                "junk",
                {"bbox": [1.0, 2.0, 3.0, 4.0], "centroid": [0.5, 0.5]},
            ],
        }
    )
    result = PybdshadowAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert len(result.findings) == 2
    assert result.findings[-1].value == "pybdshadow:shadow:4"
    assert result.findings[-1].attributes["bbox"] == [1.0, 2.0, 3.0, 4.0]


def test_pybdshadow_driver_document_validation():
    driver = _load_driver()
    when, buildings = driver._validate_document(_document())
    assert when.year == 2024 and when.hour == 12
    assert buildings[0]["building_id"] == "b1"
    assert buildings[0]["height"] == 10.0

    duplicate = _document()
    duplicate["buildings"]["features"].append(
        duplicate["buildings"]["features"][0]
    )
    too_many = _document()
    too_many["buildings"]["features"] = (
        too_many["buildings"]["features"] * (driver.MAX_BUILDINGS + 1)
    )
    hole = _document()
    ring = hole["buildings"]["features"][0]["geometry"]["coordinates"][0]
    hole["buildings"]["features"][0]["geometry"]["coordinates"] = [ring, ring]
    unclosed = _document()
    unclosed["buildings"]["features"][0]["geometry"]["coordinates"] = [[
        [0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]
    ]]

    bad = [
        _document(datetime_utc="1899-01-01T00:00:00Z"),
        _document(datetime_utc="not-a-date"),
        {**_document(), "buildings": []},
        hole,
        unclosed,
        duplicate,
        too_many,
    ]
    for document in bad:
        with pytest.raises(ValueError):
            driver._validate_document(document)

    assert driver._validate_document(_document(datetime_utc="2024-06-01T14:00:00+02:00"))[0].hour == 12
    assert driver._validate_document(_document(datetime_utc="2024-06-01T12:00:00"))[0].hour == 12
