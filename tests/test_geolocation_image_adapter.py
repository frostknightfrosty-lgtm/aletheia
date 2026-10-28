"""Parser and runner-contract tests for the geolocation_image batch adapter."""

import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.adapters.geolocation_image import (
    SUPPORTED_SUB_SOURCES,
    UNSUPPORTED_SUB_SOURCES,
    GeoEvidenceFinding,
    GeolocationImageAdapter,
)
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "geolocation_image.json"


def _request(seed_type: SeedType = SeedType.GEOLOCATION, value: str = "51.5007,-0.1246") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(),
        seed=Seed(type=seed_type, value=value),
        legal_only=True,
        authorization_assertion="Synthetic fixture parser test.",
    )


@parser_test("geolocation_image")
def test_parse_synthetic_fixture_covers_every_source():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    result = GeolocationImageAdapter().parse(
        _request(), Path("."), json.dumps(fixture), "", 0
    )

    assert result.status == "succeeded"
    assert {finding.attributes["source"] for finding in result.findings} == (
        set(SUPPORTED_SUB_SOURCES) | set(UNSUPPORTED_SUB_SOURCES)
    )
    assert len(result.findings) == 12
    assert all(isinstance(finding, GeoEvidenceFinding) for finding in result.findings)
    assert all(finding.entity_type == (EntityType.UNKNOWN if str(finding.value).endswith((":skipped", ":error")) else EntityType.GEO_EVIDENCE) for finding in result.findings)
    assert all(finding.provenance.source_url.startswith("https://") for finding in result.findings)
    assert {finding.attributes["source"] for finding in result.findings if finding.attributes.get("record_type")} == set(SUPPORTED_SUB_SOURCES)


def test_adapter_wiring_and_supported_seed_types():
    adapter = GeolocationImageAdapter()
    assert adapter.supports(SeedType.GEOLOCATION)
    assert adapter.supports(SeedType.NAME)
    assert adapter.supports(SeedType.IMAGE)
    assert adapter.supports(SeedType.FILE_PATH)
    assert not adapter.supports(SeedType.EMAIL)

    from aletheia.adapters.registry import phase7_adapters

    assert phase7_adapters()["geolocation_image"].descriptor is adapter.descriptor


def _load_runner():
    path = ROOT / "docker" / "geolocation_image" / "runner.py"
    spec = importlib.util.spec_from_file_location("geolocation_image_runner_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_http_subsources_use_bounded_documented_requests(monkeypatch):
    runner = _load_runner()
    requests = []

    def fake_fetch(url, *, headers=None):
        requests.append((url, headers))
        if "graph.mapillary.com" in url:
            return {"data": [{"id": "map-1", "computed_geometry": {"coordinates": [-0.1246, 51.5007]}}]}, 200, None
        if "nominatim.openstreetmap.org/search" in url:
            return [{"osm_type": "node", "osm_id": 1, "display_name": "Paris", "lat": "48.8", "lon": "2.3"}], 200, None
        return {
            "features": [{"id": "scene-1", "collection": "sentinel-2-l2a", "properties": {"datetime": "2026-01-15T10:00:00Z"}}]
        }, 200, None

    monkeypatch.setattr(runner, "_fetch_json", fake_fetch)
    monkeypatch.setenv("MAPILLARY_ACCESS_TOKEN", "test-token")

    mapillary = runner.query_mapillary("geolocation", "51.5007,-0.1246")
    assert mapillary.error is None
    mapillary_url, mapillary_headers = requests[0]
    mapillary_params = parse_qs(urlparse(mapillary_url).query)
    assert set(mapillary_params) == {"fields", "bbox", "limit"}
    assert mapillary_params["limit"] == ["5"]
    assert mapillary_headers == {"Authorization": "OAuth test-token"}

    nominatim = runner.query_nominatim("name", "Paris")
    assert nominatim.error is None
    nominatim_url, _ = requests[1]
    nominatim_params = parse_qs(urlparse(nominatim_url).query)
    assert nominatim_params == {"q": ["Paris"], "format": ["jsonv2"], "limit": ["5"], "addressdetails": ["1"]}

    stac = runner.query_copernicus_stac("geolocation", "51.5007,-0.1246,2026-01-01/2026-01-31")
    assert stac.error is None
    stac_url, _ = requests[2]
    stac_params = parse_qs(urlparse(stac_url).query)
    assert set(stac_params) == {"bbox", "datetime", "limit"}
    assert stac_params["datetime"] == ["2026-01-01/2026-01-31"]
    assert stac_params["limit"] == ["5"]


def test_mapillary_without_token_is_audited_skip_without_request(monkeypatch):
    runner = _load_runner()
    monkeypatch.delenv("MAPILLARY_ACCESS_TOKEN", raising=False)

    def forbidden_fetch(*args, **kwargs):
        raise AssertionError("Mapillary must not be called without its free token")

    monkeypatch.setattr(runner, "_fetch_json", forbidden_fetch)
    result = runner.query_mapillary("geolocation", "51.5007,-0.1246")
    assert result.skipped
    assert "MAPILLARY_ACCESS_TOKEN" in result.skip_reason


def test_local_image_tools_use_only_bounded_analysis_commands(monkeypatch, tmp_path):
    runner = _load_runner()
    commands = []

    def fake_run(argv):
        commands.append(argv)
        if argv[0] == "dfit":
            report = Path(argv[5])
            report.write_text('{"metadata": {"camera": "fixture"}}', encoding="utf-8")
        else:
            report_dir = Path(argv[-1])
            report_dir.mkdir(parents=True)
            (report_dir / "analysis.json").write_text('{"metadata": {}, "ela": {}}', encoding="utf-8")
        return 0, "", "", None

    monkeypatch.setattr(runner, "_run_tool", fake_run)
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"synthetic-image-bytes")

    dfit = runner.query_dfit("image", str(image))
    steg = runner.query_steg_analyzer("image", str(image))

    assert dfit.error is None and dfit.data["records"][0]["source_fields"]["top_level_keys"] == ["metadata"]
    assert steg.error is None and steg.data["records"][0]["source_fields"]["top_level_keys"] == ["ela", "metadata"]
    assert commands[0][:5] == ["dfit", "metadata", "-i", str(image), "-o"]
    assert commands[1] == [
        "steg-analyzer", "analyze", str(image), "--metadata", "--ela", "--histogram",
        "--format", "json", "--output", commands[1][-1],
    ]
    assert not any(token in {"extract", "crack", "password", "wordlist"} for cmd in commands for token in cmd)


def test_image_seed_is_staged_to_the_container_mount(tmp_path):
    adapter = GeolocationImageAdapter()
    source = tmp_path / "evidence.jpg"
    source.write_bytes(b"fixture")
    workspace = tmp_path / "workspace"

    command = adapter.build_command(_request(SeedType.IMAGE, str(source)), workspace)

    assert command == ["image", "/work/geolocation-image-input.jpg"]
    assert (workspace / "geolocation-image-input.jpg").read_bytes() == b"fixture"
