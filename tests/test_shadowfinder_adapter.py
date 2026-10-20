"""Fixture/parser and driver tests for the ShadowFinder adapter.

The parser test runs on ``tests/fixtures/shadowfinder.json`` — a synthetic
document in the exact shape the pinned driver prints (see
``docker/shadowfinder``). Driver checks import the driver file directly; nothing
here needs the upstream package, network access, or Docker.

The ``@parser_test("shadowfinder")`` marker pins parser coverage for the parser
pre-flight.
"""

import importlib.util
import json
import math
from pathlib import Path
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.adapters.shadowfinder import ShadowFinderAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "shadowfinder.json"
OBSERVATION = "height=10;shadow=5;datetime=2024-06-01T12:00:00Z"


def _request(value=OBSERVATION):
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.SHADOW_OBSERVATION, value=value)
    )


def _load_driver():
    path = ROOT / "docker" / "shadowfinder" / "run_shadowfinder.py"
    spec = importlib.util.spec_from_file_location("shadowfinder_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_shadowfinder_descriptor_scoping():
    adapter = ShadowFinderAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "shadowfinder"
    assert descriptor.license == "MIT"
    assert descriptor.input_types == [SeedType.SHADOW_OBSERVATION]
    assert descriptor.output_types == [EntityType.GEO_EVIDENCE]
    assert descriptor.network_required is False
    assert descriptor.requires_authorization_assertion is False
    assert descriptor.docker_image == "aletheia/shadowfinder:v1"
    assert descriptor.upstream == "https://github.com/bellingcat/ShadowFinder"
    assert "215485abd5a46a9b98c4ba0fbfce7df6b6bb1be8" in descriptor.version_pin
    assert adapter.supports(SeedType.SHADOW_OBSERVATION) is True
    assert adapter.supports(SeedType.GEOLOCATION) is False


def test_shadowfinder_build_command_observation():
    command = ShadowFinderAdapter().build_command(_request(), Path("."))
    assert command == ["--observation", OBSERVATION]


@parser_test("shadowfinder")
def test_shadowfinder_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = ShadowFinderAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert json.loads(stdout)["pinned_commit"] in ShadowFinderAdapter.descriptor.version_pin
    assert _values(result) == [
        "shadowfinder:candidate:1",
        "shadowfinder:candidate:2",
        "shadowfinder:run:ok",
    ]
    assert len(result.findings) == 3
    assert all(finding.entity_type == EntityType.GEO_EVIDENCE for finding in result.findings)

    by_value = {finding.value: finding for finding in result.findings}
    run = by_value["shadowfinder:run:ok"]
    assert run.attributes["status"] == "ok"
    assert run.attributes["observation"] == {
        "height_m": 10.0,
        "shadow_length_m": 5.0,
        "datetime_utc": "2024-06-01T12:00:00Z",
    }
    assert run.attributes["grid"]["cells_total"] == 208800
    assert run.attributes["thresholds"]["tolerance"] == 0.1
    assert run.attributes["regions_total"] == 2
    assert run.attributes["truncated"] is False
    assert run.provenance.confidence == 0.3

    first = by_value["shadowfinder:candidate:1"]
    assert first.attributes["rank"] == 1
    assert first.attributes["bbox"] == [0.0, -30.0, 1.0, -29.0]
    assert first.attributes["centroid"] == [0.5, -29.5]
    assert first.attributes["best_cell"]["relative_difference"] == -0.002
    assert first.attributes["cell_count"] == 6
    assert first.attributes["tolerance"] == 0.1
    assert first.provenance.confidence == 0.4


def test_shadowfinder_parser_invalid_target_document():
    stdout = json.dumps({
        "source": "shadowfinder",
        "status": "invalid_target",
        "error": "expected --observation height=<metres>;shadow=<metres>;datetime=<UTC ISO-8601>",
    })
    result = ShadowFinderAdapter().parse(_request(), Path("."), stdout, "", 2)
    assert _values(result) == ["shadowfinder:run:invalid_target"]
    assert result.findings[0].attributes["reason"].startswith("expected --observation")
    assert result.status == "partial"


def test_shadowfinder_parser_no_candidates_and_empty_stdout():
    stdout = json.dumps({
        "source": "shadowfinder",
        "status": "no_candidates",
        "candidates": [],
        "regions_total": 0,
        "truncated": False,
    })
    result = ShadowFinderAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert _values(result) == ["shadowfinder:run:no_candidates"]
    assert result.findings[0].attributes["truncated"] is False

    empty = ShadowFinderAdapter().parse(_request(), Path("."), "", "boom", 1)
    assert _values(empty) == ["shadowfinder:run:unknown"]
    assert empty.findings[0].attributes["status"] == "unknown"


def test_shadowfinder_parser_ignores_malformed_candidates():
    stdout = json.dumps({
        "status": "ok",
        "thresholds": {"tolerance": 0.1},
        "candidates": [
            "not-a-dict",
            {
                "rank": "first",
                "bbox": [0.0, 1.0, 2.0],
                "centroid": [1.0, 2.0, 3.0],
                "best_cell": {"lat": "x", "lon": 2.0, "relative_difference": 0.01},
                "cell_count": True,
            },
            {
                "rank": 2,
                "bbox": [10.0, 20.0, 11.0, 21.0],
                "centroid": [10.5, 20.5],
                "best_cell": {"lat": 10.5, "lon": 20.5, "relative_difference": 0.04},
                "cell_count": 3,
            },
        ],
    })
    result = ShadowFinderAdapter().parse(_request(), Path("."), stdout, "", 0)
    values = _values(result)
    assert values == [
        "shadowfinder:candidate:2",
        "shadowfinder:candidate:3",
        "shadowfinder:run:ok",
    ]
    second = next(f for f in result.findings if f.value == "shadowfinder:candidate:2")
    assert second.attributes["rank"] == 2
    assert "bbox" not in second.attributes
    assert "cell_count" not in second.attributes
    third = next(f for f in result.findings if f.value == "shadowfinder:candidate:3")
    assert third.attributes["bbox"] == [10.0, 20.0, 11.0, 21.0]
    assert third.attributes["cell_count"] == 3


def test_shadowfinder_driver_observation_parsing():
    driver = _load_driver()
    parsed = driver._parse_observation(OBSERVATION)
    assert parsed is not None
    public, when = parsed
    assert public == {
        "height_m": 10.0,
        "shadow_length_m": 5.0,
        "datetime_utc": "2024-06-01T12:00:00Z",
    }
    assert when.tzinfo is None
    assert when.year == 2024 and when.hour == 12

    offset = driver._parse_observation(
        "height=10&shadow=5&datetime=2024-06-01T14:00:00+02:00"
    )
    assert offset is not None and offset[0]["datetime_utc"] == "2024-06-01T12:00:00Z"
    naive = driver._parse_observation("height=10;shadow=5;datetime=2024-06-01T12:00:00")
    assert naive is not None and naive[0]["datetime_utc"] == "2024-06-01T12:00:00Z"

    for bad in (
        "",
        "height=10;shadow=5",
        "height=0;shadow=5;datetime=2024-06-01T12:00:00Z",
        "height=-1;shadow=5;datetime=2024-06-01T12:00:00Z",
        "height=nan;shadow=5;datetime=2024-06-01T12:00:00Z",
        "height=inf;shadow=5;datetime=2024-06-01T12:00:00Z",
        "height=10;shadow=5;datetime=2024-06-01",
        "height=10;shadow=5;datetime=1800-06-01T12:00:00Z",
        "height=10;shadow=5;datetime=2200-06-01T12:00:00Z",
        "height=10;height=11;shadow=5;datetime=2024-06-01T12:00:00Z",
        "height=10;shadow=5;datetime=2024-06-01T12:00:00Z;extra=1",
        "height=10;shadow=5;datetime",
    ):
        assert driver._parse_observation(bad) is None, bad


def test_shadowfinder_driver_candidate_binning():
    driver = _load_driver()
    candidates, matching, regions, evaluated = driver._bin_candidates(
        [[10.0, 10.0], [11.0, 11.0]],
        [[20.0, 21.0], [20.0, 21.0]],
        [[0.01, 0.2], [0.05, 0.5]],
        tolerance=0.1,
        bin_deg=1.0,
        max_regions=5,
    )
    assert (matching, regions, evaluated) == (2, 2, 4)
    assert len(candidates) == 2
    assert candidates[0]["bbox"] == [10.0, 20.0, 11.0, 21.0]
    assert candidates[0]["cell_count"] == 1
    assert candidates[0]["best_cell"]["relative_difference"] == 0.01
    assert candidates[1]["bbox"] == [11.0, 20.0, 12.0, 21.0]

    boundary = driver._bin_candidates(
        [[0.0]], [[0.0]], [[0.1]], tolerance=0.1, bin_deg=1.0, max_regions=5
    )
    assert boundary[1] == 1

    truncated = driver._bin_candidates(
        [[0.0, 0.0]], [[0.0, 2.0]], [[0.01, 0.02]],
        tolerance=0.1, bin_deg=1.0, max_regions=1,
    )
    assert len(truncated[0]) == 1 and truncated[2] == 2

    ignored = driver._bin_candidates(
        [[0.0, 0.0]], [[0.0, 1.0]], [[math.nan, math.inf]],
        tolerance=0.1, bin_deg=1.0, max_regions=5,
    )
    assert ignored[0] == [] and ignored[1] == 0 and ignored[3] == 0


def test_shadowfinder_driver_args():
    driver = _load_driver()
    parsed = driver._parse_args(["--observation", OBSERVATION])
    assert parsed is not None
    assert parsed["tolerance"] == 0.1
    assert parsed["bin_deg"] == 1.0
    assert parsed["max_regions"] == 20
    assert parsed["step"] == 1

    full = driver._parse_args([
        "--observation", OBSERVATION, "--tolerance", "0.05", "--bin-deg", "0.5",
        "--max-regions", "5", "--step", "2",
    ])
    assert full == {
        "observation": OBSERVATION,
        "tolerance": 0.05,
        "bin_deg": 0.5,
        "max_regions": 5,
        "step": 2,
    }

    for bad in (
        [],
        ["--observation"],
        ["--observation", OBSERVATION, "--tolerance", "0"],
        ["--observation", OBSERVATION, "--tolerance", "0.6"],
        ["--observation", OBSERVATION, "--bin-deg", "0.1"],
        ["--observation", OBSERVATION, "--bin-deg", "6"],
        ["--observation", OBSERVATION, "--max-regions", "0"],
        ["--observation", OBSERVATION, "--max-regions", "51"],
        ["--observation", OBSERVATION, "--step", "0"],
        ["--observation", OBSERVATION, "--step", "5"],
        ["--observation", OBSERVATION, "--unknown", "1"],
        ["--health"],
    ):
        assert driver._parse_args(bad) is None, bad
