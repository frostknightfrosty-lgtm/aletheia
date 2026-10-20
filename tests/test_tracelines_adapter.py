"""Fixture/parser and driver tests for the tracelines adapter.

The parser test runs on ``tests/fixtures/tracelines.json`` — a synthetic
document in the exact shape the pinned driver prints (see
``docker/tracelines``). Driver checks import the driver file directly; nothing
here needs the upstream checkout, network access, or Docker.

The ``@parser_test("tracelines")`` marker pins parser coverage for the
parser pre-flight.
"""

import importlib.util
import json
import types
from pathlib import Path
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.adapters.tracelines import TracelinesAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "tracelines.json"


def _request(seed_type=SeedType.GEOLOCATION, value="44.4400,26.1000"):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=seed_type, value=value))


def _load_driver():
    path = ROOT / "docker" / "tracelines" / "run_tracelines.py"
    spec = importlib.util.spec_from_file_location("tracelines_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_tracelines_descriptor_scoping():
    adapter = TracelinesAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "tracelines"
    assert descriptor.license == "AGPL-3.0-or-later"
    assert descriptor.input_types == [SeedType.GEOLOCATION]
    assert descriptor.output_types == [EntityType.UNKNOWN]
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.docker_image == "aletheia/tracelines:v1"
    assert descriptor.upstream == "https://github.com/Prekzursil/tracelines"
    assert "99257f0519b30ce7d890db25252f6cf440fa102e" in descriptor.version_pin
    assert adapter.supports(SeedType.GEOLOCATION) is True
    assert adapter.supports(SeedType.IMAGE) is False


def test_tracelines_build_command_point():
    command = TracelinesAdapter().build_command(_request(), Path("."))
    assert command == ["--point", "44.4400,26.1000"]


@parser_test("tracelines")
def test_tracelines_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = TracelinesAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert json.loads(stdout)["pinned_commit"] in TracelinesAdapter.descriptor.version_pin
    assert _values(result) == [
        "tracelines:kartaview:ok",
        "tracelines:mapillary:skipped",
        "tracelines:segment:kartaview:kv-101",
        "tracelines:segment:kartaview:kv-102",
    ]
    assert len(result.findings) == 4

    by_value = {finding.value: finding for finding in result.findings}
    mapillary = by_value["tracelines:mapillary:skipped"]
    assert mapillary.attributes["reason"] == "no MAPILLARY_TOKEN in env"
    assert mapillary.attributes["stats"] == {"skipped": "no MAPILLARY_TOKEN in env"}
    assert mapillary.attributes["segments_total"] == 0

    first = by_value["tracelines:segment:kartaview:kv-101"]
    assert first.entity_type == EntityType.UNKNOWN
    assert first.attributes["length_m"] == 212.4
    assert first.attributes["n_points"] == 4
    assert first.attributes["centroid"] == [26.1, 44.44]
    assert first.attributes["capture_date"] == "2024-05-01T00:00:00Z"
    assert first.attributes["attribution"].startswith("\u00a9 KartaView")
    assert first.attributes["bbox"] == [26.09613, 44.437306, 26.10387, 44.442694]
    assert all(finding.entity_type == EntityType.UNKNOWN for finding in result.findings)


def test_tracelines_parser_invalid_target_document():
    stdout = json.dumps({
        "source": "tracelines",
        "target": "91,0",
        "status": "invalid_target",
        "sources": {},
        "error": "expected --point LAT,LON with lat in [-90,90] and lon in [-180,180]",
    })
    result = TracelinesAdapter().parse(_request(value="91,0"), Path("."), stdout, "", 2)
    assert [finding.value for finding in result.findings] == ["tracelines:run:invalid_target"]
    assert result.findings[0].attributes["reason"].startswith("expected --point")


def test_tracelines_parser_blocked_and_deadline_documents():
    blocked = json.dumps({
        "source": "tracelines",
        "target": "44.44,26.10",
        "status": "blocked",
        "sources": {},
        "error": "403 Forbidden",
    })
    result = TracelinesAdapter().parse(_request(), Path("."), blocked, "", 0)
    assert [finding.value for finding in result.findings] == ["tracelines:run:blocked"]

    deadline = json.dumps({
        "source": "tracelines",
        "target": "44.44,26.10",
        "status": "error",
        "deadline_exceeded": True,
        "sources": {},
        "error": "hard deadline of 180s exceeded",
    })
    result = TracelinesAdapter().parse(_request(), Path("."), deadline, "", 3)
    assert [finding.value for finding in result.findings] == ["tracelines:run:deadline_exceeded"]
    assert result.findings[0].attributes["status"] == "deadline_exceeded"


def test_tracelines_parser_ignores_malformed_sources_and_segments():
    stdout = json.dumps({
        "source": "tracelines",
        "target": "44.44,26.10",
        "status": "ok",
        "sources": {
            "kartaview": {
                "status": "ok",
                "segments": [
                    "not-a-dict",
                    {"id": "", "length_m": "long", "n_points": True, "centroid": [1, 2, 3]},
                ],
            },
            "mapillary": "not-a-dict",
        },
    })
    result = TracelinesAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert _values(result) == [
        "tracelines:kartaview:ok",
        "tracelines:mapillary:error",
        "tracelines:segment:kartaview:segment-1",
    ]
    segment = next(finding for finding in result.findings if ":segment:" in finding.value)
    assert "length_m" not in segment.attributes
    assert "n_points" not in segment.attributes
    assert "centroid" not in segment.attributes

    empty = TracelinesAdapter().parse(_request(), Path("."), "", "", 1)
    assert empty.findings == []


def test_tracelines_driver_point_and_bbox_math():
    driver = _load_driver()
    assert driver._parse_point("37.7749,-122.4194") == (37.7749, -122.4194)
    assert driver._parse_point(" 37.7 , -122.4 ") == (37.7, -122.4)
    assert driver._parse_point("91,0") is None
    assert driver._parse_point("-91,0") is None
    assert driver._parse_point("0,181") is None
    assert driver._parse_point("nan,0") is None
    assert driver._parse_point("37.7") is None
    assert driver._parse_point("a,b") is None

    bbox = driver._bbox_for_point(0.0, 0.0, driver.DEFAULT_RADIUS_M)
    assert bbox[0] < 0.0 < bbox[2]
    assert bbox[1] < 0.0 < bbox[3]
    assert abs((bbox[2] - bbox[0]) - (bbox[3] - bbox[1])) < 1e-6
    clamped = driver._bbox_for_point(89.99, 179.9999, driver.MAX_RADIUS_M)
    assert clamped[0] >= -180.0 and clamped[2] <= 180.0
    assert clamped[1] >= -90.0 and clamped[3] <= 90.0


def test_tracelines_driver_args_and_status_helpers():
    driver = _load_driver()
    assert driver._parse_args(["--point", "44.44,26.10"]) == ("44.44,26.10", driver.DEFAULT_RADIUS_M)
    assert driver._parse_args(["--point", "44.44,26.10", "--radius", "100"]) == ("44.44,26.10", 100.0)
    assert driver._parse_args(["--point", "44.44,26.10", "--radius", "10000"])[1] <= driver.MAX_RADIUS_M
    assert driver._parse_args([]) is None
    assert driver._parse_args(["--point"]) is None
    assert driver._parse_args(["--point", "1,2", "--radius", "-1"]) is None
    assert driver._parse_args(["--point", "1,2", "extra"]) is None

    assert driver._source_status({"skipped": "no token"}, []) == ("skipped", "no token")
    assert driver._source_status({"unavailable": "missing dep"}, []) == ("skipped", "missing dep")
    status, reason = driver._source_status({"error": "403 Forbidden"}, [])
    assert status == "blocked"
    assert reason == "403 Forbidden"
    assert driver._source_status({"error": "ConnectionResetError: boom"}, [])[0] == "error"
    assert driver._source_status({}, []) == ("empty", "")
    assert driver._source_status({}, [object()]) == ("ok", "")
    assert driver._source_status({"tiles_failed": 2}, [])[0] == "error"
    assert driver._source_status({"note": "no KartaView host responded"}, [])[0] == "error"

    assert driver._derive_run_status({"mapillary": "ok", "kartaview": "blocked"}) == "ok"
    assert driver._derive_run_status({"mapillary": "skipped", "kartaview": "empty"}) == "empty"
    assert driver._derive_run_status({"mapillary": "blocked", "kartaview": "blocked"}) == "blocked"
    assert driver._derive_run_status({"mapillary": "error", "kartaview": "blocked"}) == "error"
    assert driver._derive_run_status({"mapillary": "skipped", "kartaview": "skipped"}) == "empty"
    assert driver._looks_blocked("HTTP 429 Too Many Requests") is True
    assert driver._looks_blocked("ReadTimeout: timed out") is False


def test_tracelines_driver_segment_summary():
    driver = _load_driver()
    segment = types.SimpleNamespace(
        id="kv-9",
        coords=[(26.10, 44.44), (26.11, 44.44), (26.12, 44.44)],
        source=types.SimpleNamespace(value="kartaview"),
        capture_date="2024-01-01",
        is_pano=None,
        length_m=333.0,
    )
    summary = driver._summarize_segment(segment)
    assert summary["id"] == "kv-9"
    assert summary["source"] == "kartaview"
    assert summary["n_points"] == 3
    assert summary["start"] == (26.10, 44.44)
    assert summary["end"] == (26.12, 44.44)
    assert summary["centroid"] == [26.11, 44.44]
    assert summary["length_m"] > 0
    assert summary["attribution"].startswith("\u00a9 KartaView")
