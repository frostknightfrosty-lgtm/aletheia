"""Fixture/parser and driver tests for the Zehef email adapter.

The parser test runs on ``tests/fixtures/zehef.json`` — a synthetic document
in the exact shape the pinned driver prints (see ``docker/zehef``). Driver
checks import the driver file directly; nothing here needs the upstream
checkout or network access.
"""

import asyncio
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.adapters.identity import ZehefAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "zehef.json"


def _request(value="alice@example.com"):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=SeedType.EMAIL, value=value))


def _load_driver():
    path = ROOT / "docker" / "zehef" / "run_zehef.py"
    spec = importlib.util.spec_from_file_location("zehef_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@parser_test("zehef")
def test_zehef_parser_emits_only_positive_registration_findings():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = ZehefAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    services = sorted(f.value for f in result.findings if f.entity_type == EntityType.SERVICE)
    assert services == ["bandlab", "duolingo", "flickr", "github", "gravatar", "protonmail", "spotify"]
    urls = sorted(f.value for f in result.findings if f.entity_type == EntityType.URL)
    assert urls == [
        "https://github.com/alice-example",
        "https://gravatar.com/alice/",
        "https://www.flickr.com/people/1234@N00/",
    ]
    github = next(f for f in result.findings if f.value == "github")
    assert github.attributes["email"] == "alice@example.com"
    assert github.attributes["account_status"] == "registered_signal"
    assert github.attributes["username"] == "alice-example"
    assert github.attributes["name"] == "Alice Example"
    assert github.attributes["account_created"] == "2011-01-25 18:44:36"
    assert github.attributes["account_updated"] == "2024-10-01 00:00:00"
    # Non-identity detail fields are deliberately not carried into findings.
    assert "id" not in github.attributes
    assert "avatar" not in github.attributes
    assert "chess: error (ReadTimeout)" in result.stderr_tail
    assert "instagram: error (KeyError)" in result.stderr_tail
    assert len(result.findings) == 10


def test_zehef_parser_ignores_negative_and_unparsable_payloads():
    result = ZehefAdapter().parse(_request(), Path("."), "not-json", "", 1)
    assert result.findings == []
    assert result.status == "partial"


def test_zehef_parser_rejects_non_allowlisted_uris():
    stdout = json.dumps({
        "sub_source": "zehef",
        "email": "alice@example.com",
        "modules": [
            {"service": "github", "status": "registered", "details": {"account": "http://evil.example/internal"}, "output": ""},
            {"service": "protonmail", "status": "registered", "details": {"account": "https://pet-rats.example/alice"}, "output": ""},
            {"service": "spotify", "status": "registered", "details": {"account": "https://user:pass@github.com/x"}, "output": ""},
        ],
    })
    result = ZehefAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert [f.entity_type for f in result.findings] == [EntityType.SERVICE] * 3


def test_zehef_descriptor_is_registered_and_keyless():
    from aletheia.adapters.registry import phase7_adapters

    adapter = phase7_adapters()["zehef"]
    descriptor = adapter.descriptor
    assert descriptor.input_types == [SeedType.EMAIL]
    assert descriptor.output_types == [EntityType.SERVICE, EntityType.URL]
    assert descriptor.docker_image == "aletheia/zehef:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == []
    assert descriptor.parser_test_exempt is False
    assert "5b0c120efe846eae944dfea9410f925ca3036103" in descriptor.version_pin


def test_zehef_build_command_passes_the_email():
    adapter = ZehefAdapter()
    assert adapter.build_command(_request(), None) == ["alice@example.com"]


# -- driver -------------------------------------------------------------------


def test_driver_module_inventory_covers_accounts_only():
    driver = _load_driver()
    assert len(driver.MODULE_NAMES) == 17
    for forbidden in ("pastedumper", "hudsonrock", "emails_gen"):
        assert forbidden not in driver.MODULE_NAMES
    assert driver.MODULE_NAMES[-1] == "twitter"


def test_driver_classification_and_detail_parsing():
    driver = _load_driver()
    assert driver._classify(driver.GREEN_MARK + "> Spotify\n") == "registered"
    assert driver._classify(driver.RED_MARK + "> Spotify\n") == "not_registered"
    assert driver._classify(driver.RED_MARK + "> Instagram error: KeyError\n") == "error"
    assert driver._classify("") == "no_signal"
    cleaned = driver._clean(
        driver.GREEN_MARK + "> Github\n"
        "  \u251c\u2500\u2500> Username : octocat\n"
        "  \u251c\u2500\u2500> Created on : 2011-01-25 18:44:36\n"
        "  \u2514\u2500\u2500> Account : https://github.com/octocat\n"
    )
    assert driver.GREEN_MARK not in cleaned
    details = driver._parse_details(cleaned)
    assert details["username"] == "octocat"
    assert details["created_on"] == "2011-01-25 18:44:36"
    assert details["account"] == "https://github.com/octocat"


def test_driver_selftest_passes_with_a_stub_module_table():
    driver = _load_driver()
    report = driver.selftest(loader=lambda: [(name, lambda email: None) for name in driver.MODULE_NAMES])
    assert report["zehef_selftest"] == "ok"
    assert all(check["ok"] for check in report["checks"])


def test_driver_selftest_reports_a_missing_checkout():
    driver = _load_driver()

    def loader():
        raise RuntimeError("no checkout")

    report = driver.selftest(loader=loader)
    assert report["zehef_selftest"] == "fail"
    import_check = next(check for check in report["checks"] if check["name"] == "checkout_import")
    assert import_check["ok"] is False
    assert "no checkout" in report["checkout_import_error"]


def test_driver_run_email_captures_module_statuses():
    driver = _load_driver()

    async def registered(email):
        print(driver.GREEN_MARK + "> Spotify")

    async def negative(email):
        print(driver.RED_MARK + "> Adobe")

    async def broken(email):
        raise RuntimeError("boom")

    def sync_registered(email):
        print(driver.GREEN_MARK + "> Imgur")

    records = asyncio.run(driver.run_email("alice@example.com", [
        ("spotify", registered),
        ("adobe", negative),
        ("chess", broken),
        ("imgur", sync_registered),
    ]))
    statuses = {record["service"]: record["status"] for record in records}
    assert statuses == {
        "spotify": "registered",
        "adobe": "not_registered",
        "chess": "error",
        "imgur": "registered",
    }
    chess = next(record for record in records if record["service"] == "chess")
    assert chess["error"] == "RuntimeError"
    assert records[1]["output"] == "> Adobe\n"
