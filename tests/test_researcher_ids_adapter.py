"""Fixture/parser and driver tests for the researcher_ids composite adapter.

The parser test runs on ``tests/fixtures/researcher_ids.json`` — a synthetic
combined document in the exact shape ``docker/researcher_ids/run_researcher_ids.py``
emits. No live Wikidata or ORCID query is made by this test module.
"""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.researcher_ids import ResearcherIdsAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "researcher_ids.json"
NAME = "Ada Example"


def _request(value=NAME):
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.PERSON_NAME, value=value)
    )


def _load_driver():
    path = ROOT / "docker" / "researcher_ids" / "run_researcher_ids.py"
    spec = importlib.util.spec_from_file_location("researcher_ids_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_researcher_ids_descriptor_scoping():
    adapter = ResearcherIdsAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "researcher_ids"
    assert "CC0" in descriptor.license
    assert descriptor.input_types == [SeedType.PERSON_NAME]
    assert descriptor.output_types == [EntityType.PERSON]
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.docker_image == "aletheia/researcher-ids:v1"
    assert descriptor.upstream.startswith("https://www.wikidata.org/")
    assert "https://pub.orcid.org/" in descriptor.upstream
    assert adapter.supports(SeedType.PERSON_NAME) is True
    assert adapter.supports(SeedType.NAME) is False


def test_researcher_ids_build_command_writes_one_name(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = ResearcherIdsAdapter().build_command(_request("  Ada   Example  "), workspace)
    assert command == ["/work/name.txt"]
    assert (workspace / "name.txt").read_text(encoding="utf-8") == NAME + "\n"

    for bad in ("two\nlines", "x" * 241):
        with pytest.raises(ValueError):
            ResearcherIdsAdapter().build_command(_request(bad), workspace)


@parser_test("researcher_ids")
def test_researcher_ids_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = ResearcherIdsAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert result.status == "succeeded"
    assert _values(result) == [
        "researcher_ids:orcid:0000-0002-1825-0097",
        "researcher_ids:run:ok",
        "researcher_ids:wikidata:Q999001",
    ]
    assert len(result.findings) == 3
    assert all(f.entity_type == EntityType.PERSON for f in result.findings)

    by_value = {finding.value: finding for finding in result.findings}
    run = by_value["researcher_ids:run:ok"]
    assert run.attributes["query"] == NAME
    assert run.attributes["wikidata_num_found"] == 1
    assert run.attributes["wikidata_returned"] == 1
    assert run.attributes["orcid_num_found"] == 1
    assert run.attributes["orcid_returned"] == 1
    assert run.attributes["errors"] == []
    assert run.provenance.confidence == 0.2

    wiki = by_value["researcher_ids:wikidata:Q999001"]
    assert wiki.attributes["rank"] == 1
    assert wiki.attributes["human"] is True
    assert wiki.attributes["birth_date"] == "1815-12-10"
    assert wiki.attributes["occupation"] == ["mathematician"]
    assert wiki.attributes["ids"]["viaf"] == "999000001"
    assert wiki.provenance.confidence == 0.4

    orcid = by_value["researcher_ids:orcid:0000-0002-1825-0097"]
    assert orcid.attributes["institutions"] == ["Example University"]
    assert "email" not in orcid.attributes
    assert orcid.provenance.confidence == 0.4


def test_researcher_ids_parser_partial_preserves_results_and_errors():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["status"] = "partial"
    payload["errors"] = ["orcid: HTTP 503: Service Unavailable"]
    result = ResearcherIdsAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "partial"
    assert len(result.findings) == 3
    assert result.findings[0].attributes["errors"] == [
        "orcid: HTTP 503: Service Unavailable"
    ]


def test_researcher_ids_parser_malformed_output_never_crashes():
    result = ResearcherIdsAdapter().parse(_request(), Path("."), "not json", "", 1)
    assert _values(result) == ["researcher_ids:run:error"]
    assert result.status == "partial"
    assert len(result.findings) == 1


def test_researcher_ids_driver_normalises_bounds_and_excludes_email():
    driver = _load_driver()
    wiki, count = driver._wikidata_results(
        driver._SAMPLE_SEARCH, driver._SAMPLE_ENTITIES, driver._SAMPLE_REFS
    )
    assert count == 1
    assert wiki[0]["qid"] == "Q999001"
    assert wiki[0]["human"] is True
    assert wiki[0]["birth_date"] == "1815-12-10"
    assert wiki[0]["occupation"] == ["mathematician"]
    assert wiki[0]["ids"]["orcid"] == "0000-0002-1825-0097"

    orcid, num_found = driver._orcid_results(driver._SAMPLE_ORCID)
    assert num_found == 1
    assert orcid[0]["institutions"] == ["Example University"]
    assert "private@example.org" not in json.dumps(orcid)

    combined = {
        "source": "researcher_ids",
        "status": "ok",
        "query": "Ada Example",
        "wikidata": {"status": "ok", "num_found": 20,
                     "results": [{"qid": f"Q{i}"} for i in range(20)]},
        "orcid": {"status": "ok", "num_found": 20,
                  "results": [{"orcid": f"id{i}"} for i in range(20)]},
        "errors": ["x"] * 20,
    }
    normalised = driver._normalise(combined)
    assert normalised["status"] == "partial"
    assert len(normalised["wikidata"]["results"]) == driver.MAX_RESULTS
    assert len(normalised["orcid"]["results"]) == driver.MAX_RESULTS
    assert len(normalised["errors"]) == driver.MAX_ERRORS

    with pytest.raises(ValueError):
        driver._normalise({})
    with pytest.raises(ValueError):
        driver._normalise({"source": "other", "query": "x"})
    with pytest.raises(ValueError):
        driver._normalise({"source": "researcher_ids", "query": "", "status": "ok"})


def test_researcher_ids_driver_name_file_query_and_args(tmp_path):
    driver = _load_driver()
    good = tmp_path / "name.txt"
    good.write_text("  Ada   Example \n", encoding="utf-8")
    assert driver._read_name(good) == NAME

    both = tmp_path / "both.txt"
    both.write_text(NAME + "\n" + NAME + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        driver._read_name(both)
    with pytest.raises(ValueError):
        driver._read_name(tmp_path / "missing.txt")
    quote = tmp_path / "quote.txt"
    quote.write_text('Ada "Example"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        driver._read_name(quote)

    parts = driver._query_parts(NAME)
    assert parts["given"] == "Ada"
    assert parts["family"] == "Example"
    assert parts["mode"] == "fielded"
    assert parts["query"] == 'given-names:"Ada" AND family-name:"Example"'
    single = driver._query_parts("Plato")
    assert single["mode"] == "text"
    assert single["query"] == 'text:"Plato"'

    assert driver._parse_args(["--health"]).health is True
    assert driver._parse_args(["--selftest"]).selftest is True
    parsed = driver._parse_args(["--normalize", "combined.json"])
    assert parsed.normalize == "combined.json"
    assert parsed.name_file is None
    assert driver._parse_args(["name.txt"]).name_file == "name.txt"
