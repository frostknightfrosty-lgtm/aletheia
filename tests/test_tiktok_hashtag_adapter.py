"""Fixture/parser and driver tests for the tiktok-hashtag-analysis adapter.

The parser test runs on ``tests/fixtures/tiktok_hashtag.json`` — a synthetic
document in the exact shape the pinned driver prints (see
``docker/tiktok_hashtag``). Driver checks import the driver file directly;
nothing here needs the upstream checkout, a browser, or network access.
"""

import asyncio
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

from parser_test_marker import parser_test

from aletheia.adapters.social_geo_image import TiktokHashtagAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "tiktok_hashtag.json"


def _request(value="osint"):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=SeedType.HASHTAG, value=value))


def _load_driver():
    path = ROOT / "docker" / "tiktok_hashtag" / "run_tiktok_hashtag.py"
    spec = importlib.util.spec_from_file_location("tiktok_hashtag_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@parser_test("tiktok-hashtag-analysis")
def test_tiktok_parser_emits_posts_and_unique_authors():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = TiktokHashtagAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    urls = sorted(f.value for f in result.findings if f.entity_type == EntityType.URL)
    assert urls == [
        "https://www.tiktok.com/@alice_example/video/7300000000000000001",
        "https://www.tiktok.com/@alice_example/video/7300000000000000002",
        "https://www.tiktok.com/@bob.builder/video/7300000000000000003",
        "https://www.tiktok.com/@carol_osint/video/7300000000000000004",
    ]
    handles = sorted(f.value for f in result.findings if f.entity_type == EntityType.SOCIAL_ACCOUNT)
    assert handles == ["alice_example", "bob.builder", "carol_osint"]
    alice = next(f for f in result.findings if f.value == "alice_example")
    assert alice.attributes == {
        "platform": "tiktok",
        "hashtag": "osint",
        "posts_in_sample": 2,
        "example_post_url": "https://www.tiktok.com/@alice_example/video/7300000000000000001",
    }
    post = next(f for f in result.findings if f.value.endswith("0000000000001"))
    assert post.attributes["post_id"] == "7300000000000000001"
    assert post.attributes["cohashtags"] == ["newmusic", "osint"]
    assert "candidate, not a verified identity" in post.provenance.notes[0]
    assert len(result.findings) == 7


def test_tiktok_parser_ignores_unparsable_payloads():
    result = TiktokHashtagAdapter().parse(_request(), Path("."), "not-json", "", 1)
    assert result.findings == []
    assert result.status == "partial"


def test_tiktok_parser_rejects_non_post_urls_and_bad_handles():
    stdout = json.dumps({
        "hashtag": "osint",
        "status": "ok",
        "posts": [
            {"id": "11111", "url": "http://www.tiktok.com/@alice/video/11111", "author": "alice", "cohashtags": []},
            {"id": "22222", "url": "https://evil.example/@alice/video/22222", "author": "alice", "cohashtags": []},
            {"id": "33333", "url": "https://www.tiktok.com/@bad handle/video/33333", "author": "bad handle", "cohashtags": []},
            {"id": "44444", "url": "https://www.tiktok.com/@good_handle/video/44444", "author": "good_handle", "cohashtags": ["tag"]},
        ],
    })
    result = TiktokHashtagAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert [f.value for f in result.findings] == [
        "https://www.tiktok.com/@good_handle/video/44444",
        "good_handle",
    ]
    assert result.findings[0].attributes["post_id"] == "44444"
    assert result.findings[0].attributes["cohashtags"] == ["tag"]


def test_tiktok_parser_records_blocked_status_as_a_marker():
    stdout = json.dumps({
        "hashtag": "osint",
        "status": "blocked",
        "posts": [],
        "error": "EmptyResponseException: TikTok sent back an empty response.",
    })
    result = TiktokHashtagAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert len(result.findings) == 1
    marker = result.findings[0]
    assert marker.entity_type == EntityType.UNKNOWN
    assert marker.value == "tiktok-hashtag-analysis:blocked"
    assert marker.attributes["status"] == "blocked"
    assert "EmptyResponseException" in marker.attributes["reason"]


def test_tiktok_descriptor_is_registered_and_keyless():
    from aletheia.adapters.registry import phase7_adapters

    adapter = phase7_adapters()["tiktok-hashtag-analysis"]
    descriptor = adapter.descriptor
    assert descriptor.input_types == [SeedType.HASHTAG]
    assert descriptor.output_types == [EntityType.SOCIAL_ACCOUNT, EntityType.URL, EntityType.UNKNOWN]
    assert descriptor.docker_image == "aletheia/tiktok-hashtag:v1"
    assert descriptor.health_check == "--health"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.secret_env == []
    assert descriptor.parser_test_exempt is False
    assert "2a4af674efc4af7c7d592053ec3f475555f37694" in descriptor.version_pin


def test_tiktok_build_command_passes_the_hashtag():
    adapter = TiktokHashtagAdapter()
    assert adapter.build_command(_request(), None) == ["osint"]


# -- driver -------------------------------------------------------------------


def test_driver_hashtag_validation_and_post_normalization():
    driver = _load_driver()
    assert driver._HASHTAG_RE.match("#osint")
    assert driver._HASHTAG_RE.match("OSINT")
    assert not driver._HASHTAG_RE.match("two words")
    assert not driver._HASHTAG_RE.match("")
    normalized = driver._normalize_post({
        "id": "7301234567890123456",
        "desc": "sunset vibes #NewMusic",
        "createTime": 1710000000,
        "author": {"uniqueId": "example_user"},
        "textExtra": [
            {"hashtagName": "NewMusic"},
            {"hashtagName": "newmusic"},
            {"hashtagName": "osint"},
            {"hashtagName": ""},
        ],
    })
    assert normalized == {
        "id": "7301234567890123456",
        "url": "https://www.tiktok.com/@example_user/video/7301234567890123456",
        "author": "example_user",
        "create_time": 1710000000,
        "desc_excerpt": "sunset vibes #NewMusic",
        "cohashtags": ["newmusic", "osint"],
    }
    assert driver._normalize_post({"id": "abc", "author": {"uniqueId": "example_user"}}) is None
    assert driver._normalize_post({"id": "7301234567890123456", "author": {"uniqueId": "bad handle"}}) is None
    assert driver._normalize_post({"id": "7301234567890123456", "author": {}}) is None


def test_driver_selftest_passes_with_stubs(tmp_path):
    driver = _load_driver()
    driver.CHECKOUT = str(tmp_path)
    (tmp_path / "PINNED_COMMIT").write_text(driver.PINNED_COMMIT, encoding="utf-8")

    async def stub_fetch(hashtag, limit, headed=False):
        return []

    report = driver.selftest(
        loader=lambda: (stub_fetch, "2.0.4"),
        stealth_probe=lambda: True,
        chromium_probe=lambda: True,
    )
    assert report["tiktok_hashtag_selftest"] == "ok"
    assert all(check["ok"] for check in report["checks"])
    assert report["checkout_version"] == "2.0.4"


def test_driver_selftest_reports_a_missing_checkout(tmp_path):
    driver = _load_driver()
    driver.CHECKOUT = str(tmp_path)
    (tmp_path / "PINNED_COMMIT").write_text(driver.PINNED_COMMIT, encoding="utf-8")

    def loader():
        raise RuntimeError("no checkout")

    report = driver.selftest(loader=loader, stealth_probe=lambda: True, chromium_probe=lambda: True)
    assert report["tiktok_hashtag_selftest"] == "fail"
    import_check = next(check for check in report["checks"] if check["name"] == "checkout_import")
    assert import_check["ok"] is False
    assert "no checkout" in report["checkout_import_error"]


def test_driver_fetch_maps_outcomes_and_timeouts():
    driver = _load_driver()

    class Blocked(Exception):
        pass

    async def blocked_fetch(hashtag, limit, headed=False):
        raise Blocked("empty response")

    state = {}
    status, posts, error = driver._fetch(blocked_fetch, "osint", 5, state, blocked_types=(Blocked,))
    assert (status, posts) == ("blocked", [])
    assert "Blocked" in error
    assert state["stage"] == "fetch"

    async def ok_fetch(hashtag, limit, headed=False):
        return [{"id": "1"}]

    assert driver._fetch(ok_fetch, "osint", 5, {}, blocked_types=(Blocked,)) == ("ok", [{"id": "1"}], None)

    async def broken_fetch(hashtag, limit, headed=False):
        raise ValueError("drift")

    status, _, error = driver._fetch(broken_fetch, "osint", 5, {}, blocked_types=(Blocked,))
    assert status == "error"
    assert "ValueError" in error

    driver.FETCH_TIMEOUT_SECONDS = 0.05

    async def slow_fetch(hashtag, limit, headed=False):
        await asyncio.sleep(2)
        return []

    status, _, error = driver._fetch(slow_fetch, "osint", 5, {}, blocked_types=(Blocked,))
    assert status == "error"
    assert "timed out" in error
