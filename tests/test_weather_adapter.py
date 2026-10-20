"""Fixture/parser and driver tests for the weather adapter.

The parser test runs on ``tests/fixtures/weather.json`` — a synthetic
normalized Open-Meteo forecast document. No live API request is made.
"""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.weather import WeatherAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "weather.json"
TARGET = "51.5007,-0.1246"


def _request(value=TARGET):
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.GEOLOCATION, value=value)
    )


def _load_driver():
    path = ROOT / "docker" / "weather" / "run_weather.py"
    spec = importlib.util.spec_from_file_location("weather_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_weather_descriptor_scoping():
    adapter = WeatherAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "weather"
    assert "CC-BY 4.0" in descriptor.license
    assert "non-commercial" in descriptor.legal_notes[0]
    assert descriptor.input_types == [SeedType.GEOLOCATION]
    assert descriptor.output_types == [EntityType.GEO_EVIDENCE]
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.docker_image == "aletheia/weather:v1"
    assert descriptor.upstream == "https://open-meteo.com/"
    assert adapter.supports(SeedType.GEOLOCATION) is True
    assert adapter.supports(SeedType.URL) is False


def test_weather_build_command_validates_target():
    adapter = WeatherAdapter()
    assert adapter.build_command(_request("51.5007, -0.1246"), Path(".")) == [
        "51.5007,-0.1246"
    ]
    assert adapter.build_command(
        _request("51.5007,-0.1246,2024-06-01"), Path(".")
    ) == ["51.5007,-0.1246,2024-06-01"]
    for bad in ("51.5", "91,-0.1", "51.5,-181", "51.5,-0.1,2024-13-01"):
        with pytest.raises(ValueError):
            adapter.build_command(_request(bad), Path("."))


@parser_test("weather")
def test_weather_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = WeatherAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert result.status == "succeeded"
    assert _values(result) == [
        "weather:observation:51.5007,-0.1246:2026-10-20",
        "weather:run:ok",
    ]
    assert len(result.findings) == 2
    assert all(f.entity_type == EntityType.GEO_EVIDENCE for f in result.findings)

    by_value = {finding.value: finding for finding in result.findings}
    run = by_value["weather:run:ok"]
    assert run.attributes["mode"] == "forecast_current"
    assert run.attributes["query"]["latitude"] == 51.5007
    assert run.attributes["grid"]["elevation"] == 8.0
    assert run.attributes["attribution"].startswith("Weather data by Open-Meteo.com")
    assert run.attributes["errors"] == []

    observation = by_value["weather:observation:51.5007,-0.1246:2026-10-20"]
    assert observation.attributes["observation"]["temperature_2m"] == 12.0
    assert observation.attributes["units"]["temperature_2m"] == "°C"
    assert observation.provenance.confidence == 0.8


def test_weather_parser_partial_and_malformed():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["status"] = "partial"
    payload["errors"] = ["observation time is not YYYY-MM-DD"]
    result = WeatherAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "partial"
    assert "observation time is not YYYY-MM-DD" in result.findings[0].attributes["errors"]

    result = WeatherAdapter().parse(_request(), Path("."), "not json", "", 1)
    assert _values(result) == ["weather:run:error"]
    assert result.status == "partial"


def test_weather_driver_normalises_forecast_and_archive():
    driver = _load_driver()
    forecast = driver._normalise(driver._SAMPLE_FORECAST)
    assert forecast["source"] == "weather"
    assert forecast["mode"] == "forecast_current"
    assert forecast["query"]["date"] == "2026-10-20"
    assert forecast["observation"]["temperature_2m"] == 12.0
    assert forecast["attribution"] == driver.ATTRIBUTION

    archive = driver._normalise(driver._SAMPLE_ARCHIVE)
    assert archive["mode"] == "archive"
    assert archive["query"]["date"] == "2024-06-01"
    assert archive["observation"]["temperature_2m_max"] == [16.5]

    with pytest.raises(ValueError):
        driver._normalise({})
    with pytest.raises(ValueError):
        driver._normalise({"error": True, "reason": "bad request"})


def test_weather_driver_target_and_args():
    driver = _load_driver()
    target = driver._parse_target("51.5007,-0.1246,2024-06-01")
    assert target["latitude"] == 51.5007
    assert target["longitude"] == -0.1246
    assert target["date"] == "2024-06-01"
    assert driver._parse_target("51.5007,-0.1246")["date"] is None

    for bad in ("51.5", "91,-0.1", "51.5,-181", "51.5,-0.1,2024-13-01"):
        with pytest.raises(ValueError):
            driver._parse_target(bad)

    assert driver._parse_args(["--health"]).health is True
    assert driver._parse_args(["--selftest"]).selftest is True
    parsed = driver._parse_args(["--normalize", "response.json"])
    assert parsed.normalize == "response.json"
    assert parsed.target is None
    assert driver._parse_args([TARGET]).target == TARGET
