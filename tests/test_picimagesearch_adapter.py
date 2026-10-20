"""Fixture/parser and driver tests for the picimagesearch adapter.

The parser test runs on ``tests/fixtures/picimagesearch.json`` — a synthetic
document in the exact shape the pinned driver prints (see
``docker/picimagesearch``). Driver checks import the driver file directly;
nothing here needs the upstream checkout, network access, or Docker.
"""

import importlib.util
import json
import types
from pathlib import Path
from uuid import uuid4

import pytest

from parser_test_marker import parser_test

from aletheia.adapters.social_geo_image import (
    PicImageSearchAdapter,
    _picimagesearch_item_urls,
)
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "picimagesearch.json"


def _request(seed_type=SeedType.IMAGE, value="photo.jpg"):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=seed_type, value=value))


def _load_driver():
    path = ROOT / "docker" / "picimagesearch" / "run_picimagesearch.py"
    spec = importlib.util.spec_from_file_location("picimagesearch_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _by_type(findings):
    grouped = {}
    for finding in findings:
        grouped.setdefault(finding.entity_type, []).append(finding)
    return grouped


@parser_test("picimagesearch")
def test_picimagesearch_fixture_urls_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = PicImageSearchAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert json.loads(stdout)["pinned_commit"] in PicImageSearchAdapter.descriptor.version_pin
    grouped = _by_type(result.findings)
    assert len(result.findings) == 11
    assert len(grouped[EntityType.URL]) == 7
    assert len(grouped[EntityType.UNKNOWN]) == 4
    assert sorted(f.value for f in grouped[EntityType.URL]) == [
        "https://api.trace.moe/image/6",
        "https://api.trace.moe/video/6",
        "https://ascii2d.net/search/4",
        "https://danbooru.donmai.us/posts/1",
        "https://konachan.com/post/3",
        "https://www.pixiv.net/artworks/5",
        "https://yandex.com/images/2",
    ]
    primary = next(f for f in grouped[EntityType.URL] if f.value == "https://danbooru.donmai.us/posts/1")
    assert primary.attributes["engine"] == "iqdb"
    assert primary.attributes["match_list"] == "primary"
    assert primary.attributes["similarity"] == 91.2
    assert primary.attributes["source"] == "Danbooru"
    tracemoe = next(f for f in grouped[EntityType.URL] if f.value.endswith("/video/6"))
    assert tracemoe.attributes["title_romaji"] == "Example Anime"
    assert tracemoe.attributes["episode"] == 1
    assert tracemoe.attributes["engine"] == "tracemoe"
    assert sorted(f.value for f in grouped[EntityType.UNKNOWN]) == [
        "picimagesearch:animetrace:character:Example Character [Example Work]",
        "picimagesearch:animetrace:character:Second Character",
        "picimagesearch:iqdb3d:empty",
        "picimagesearch:sauce_nao:skipped",
    ]
    skipped = next(f for f in grouped[EntityType.UNKNOWN] if f.value.endswith(":skipped"))
    assert "SAUCENAO_API_KEY" in skipped.attributes["reason"]


def test_picimagesearch_parser_blocked_run_and_engine_markers():
    document = {
        "source": "PicImageSearch",
        "status": "blocked",
        "engines": {
            "iqdb": {"status": "blocked", "error": "HTTP 429", "result_url": "https://iqdb.org/", "count": 0, "items": []},
            "tracemoe": {"status": "error", "error": "ReadTimeout: timed out", "result_url": "", "count": 0, "items": []},
        },
    }
    result = PicImageSearchAdapter().parse(_request(), Path("."), json.dumps(document), "driver notes", 0)
    values = [f.value for f in result.findings]
    assert "picimagesearch:iqdb:blocked" in values
    assert "picimagesearch:tracemoe:error" in values
    assert "picimagesearch:run:blocked" in values
    blocked = next(f for f in result.findings if f.value == "picimagesearch:iqdb:blocked")
    assert blocked.attributes["reason"] == "HTTP 429"
    assert blocked.attributes["status"] == "blocked"


def test_picimagesearch_parser_invalid_target_document():
    document = {
        "source": "PicImageSearch",
        "status": "invalid_target",
        "engines": {},
        "error": "expected an https:// image URL or an existing image file (at most 12 MB)",
    }
    result = PicImageSearchAdapter().parse(_request(), Path("."), json.dumps(document), "", 2)
    assert [f.value for f in result.findings] == ["picimagesearch:run:invalid_target"]
    assert result.findings[0].attributes["status"] == "invalid_target"


def test_picimagesearch_parser_deadline_document():
    document = {
        "source": "PicImageSearch",
        "status": "error",
        "deadline_exceeded": True,
        "engines": {},
        "error": "hard deadline of 210s exceeded",
    }
    result = PicImageSearchAdapter().parse(_request(), Path("."), json.dumps(document), "", 3)
    assert [f.value for f in result.findings] == ["picimagesearch:run:deadline_exceeded"]
    assert result.findings[0].attributes["status"] == "deadline_exceeded"


def test_picimagesearch_build_command_file_and_url(tmp_path):
    adapter = PicImageSearchAdapter()
    source = tmp_path / "evidence.jpg"
    source.write_bytes(b"\xff\xd8\xff\xe0")
    workspace = tmp_path / "workspace"
    assert adapter.build_command(_request(SeedType.IMAGE, str(source)), workspace) == ["--file", "/work/input.jpg"]
    assert adapter.build_command(_request(SeedType.URL, "https://example.com/photo.jpg"), workspace) == [
        "--url",
        "https://example.com/photo.jpg",
    ]
    assert adapter.supports(SeedType.IMAGE)
    assert adapter.supports(SeedType.FILE_PATH)
    assert adapter.supports(SeedType.URL)
    assert not adapter.supports(SeedType.USERNAME)


def test_picimagesearch_driver_derive_status():
    driver = _load_driver()
    assert driver._derive_status({}) == "empty"
    assert driver._derive_status({"a": {"status": "skipped"}}) == "empty"
    assert driver._derive_status({"a": {"status": "empty"}, "b": {"status": "blocked"}}) == "empty"
    assert driver._derive_status({"a": {"status": "ok"}, "b": {"status": "blocked"}}) == "ok"
    assert driver._derive_status(
        {"a": {"status": "blocked"}, "b": {"status": "blocked"}, "c": {"status": "skipped"}}
    ) == "blocked"
    assert driver._derive_status({"a": {"status": "error"}, "b": {"status": "blocked"}}) == "error"


def test_picimagesearch_driver_engine_request_shapes():
    driver = _load_driver()
    iqdb = types.SimpleNamespace(base_url="https://iqdb.org")
    payload = driver._engine_request("iqdb", iqdb, "https://example.com/a.jpg", None)
    assert payload == {
        "method": "post",
        "url": "https://iqdb.org",
        "data": {"url": "https://example.com/a.jpg"},
        "files": None,
    }
    payload = driver._engine_request("iqdb3d", types.SimpleNamespace(base_url="https://3d.iqdb.org"), None, b"img")
    assert payload["files"] == {"file": b"img"}
    ascii2d = types.SimpleNamespace(base_url="https://ascii2d.net/search")
    assert driver._engine_request("ascii2d", ascii2d, None, b"img")["url"] == "https://ascii2d.net/search/file"
    assert driver._engine_request("ascii2d", ascii2d, "https://example.com/a.jpg", None)["url"] == "https://ascii2d.net/search/uri"
    tracemoe = types.SimpleNamespace(base_url="https://api.trace.moe/search")
    payload = driver._engine_request("tracemoe", tracemoe, None, b"img")
    assert payload["params"] == {"anilistInfo": "", "cutBorders": "true"}
    animetrace = types.SimpleNamespace(base_url="https://api.animetrace.com/v1/search")
    payload = driver._engine_request("animetrace", animetrace, "https://example.com/a.jpg", None)
    assert payload["json"] == {"url": "https://example.com/a.jpg"}
    sauce = types.SimpleNamespace(
        base_url="https://saucenao.com/search.php",
        params=types.SimpleNamespace(add=lambda key, value: {"api_key": "k", key: value}),
    )
    payload = driver._engine_request("sauce_nao", sauce, "https://example.com/a.jpg", None)
    assert payload["params"]["url"] == "https://example.com/a.jpg"
    with pytest.raises(ValueError):
        driver._engine_request("google", iqdb, None, b"img")


def test_picimagesearch_driver_blocked_detection_and_scope():
    driver = _load_driver()
    assert driver._looks_blocked("HTTPError: 429 Too Many Requests")
    assert driver._looks_blocked("response could not be parsed: Cloudflare challenge page")
    assert not driver._looks_blocked("ReadTimeout: timed out")
    assert driver.KEYLESS_ENGINES == ("iqdb", "iqdb3d", "ascii2d", "tracemoe", "animetrace")
    assert driver.ENGINE_KEYS == driver.KEYLESS_ENGINES + ("sauce_nao",)
    for excluded in ("google", "google_lens", "yandex", "bing", "baidu", "copyseeker", "lenso", "tineye", "ehentai"):
        assert excluded in driver.EXCLUDED_ENGINES


def test_picimagesearch_driver_target_validation(tmp_path):
    driver = _load_driver()
    assert driver._validate_url("https://example.com/photo.jpg") == "https://example.com/photo.jpg"
    assert driver._validate_url("http://example.com/photo.jpg") is None
    assert driver._validate_url("ftp://example.com/photo.jpg") is None
    good = tmp_path / "good.jpg"
    good.write_bytes(b"x")
    assert driver._validate_file(str(good)) == str(good)
    assert driver._validate_file(str(tmp_path / "missing.jpg")) is None
    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")
    assert driver._validate_file(str(empty)) is None


def test_picimagesearch_driver_normalization_round_trip():
    driver = _load_driver()
    assert driver._normalization_ok() is True


def test_picimagesearch_driver_selftest_with_stub_engines(tmp_path, monkeypatch):
    driver = _load_driver()
    pin = tmp_path / "checkout"
    pin.mkdir()
    (pin / "PINNED_COMMIT").write_text(driver.PINNED_COMMIT, encoding="utf-8")
    monkeypatch.setattr(driver, "CHECKOUT", str(pin))
    stubs = {name: types.SimpleNamespace(verify_ssl=True) for name in driver.KEYLESS_ENGINES}
    report = driver.selftest(
        loader=lambda api_key=None: dict(stubs),
        ua_probe=lambda engine: "Aletheia/0.9.0 (picimagesearch)",
        package_probe=lambda: "3.12.11",
    )
    assert report["picimagesearch_selftest"] == "ok"
    assert report["engine_bindings"] == 5
    assert all(check["ok"] for check in report["checks"])


def test_picimagesearch_driver_selftest_refuses_browser_ua(tmp_path, monkeypatch):
    driver = _load_driver()
    pin = tmp_path / "checkout"
    pin.mkdir()
    (pin / "PINNED_COMMIT").write_text(driver.PINNED_COMMIT, encoding="utf-8")
    monkeypatch.setattr(driver, "CHECKOUT", str(pin))
    stubs = {name: types.SimpleNamespace(verify_ssl=True) for name in driver.KEYLESS_ENGINES}
    report = driver.selftest(
        loader=lambda api_key=None: dict(stubs),
        ua_probe=lambda engine: "Mozilla/5.0 (X11; Linux x86_64) Chrome/139.0.0.0",
        package_probe=lambda: "3.12.11",
    )
    assert report["picimagesearch_selftest"] == "fail"
    assert next(c for c in report["checks"] if c["name"] == "ua_honest")["ok"] is False


def test_picimagesearch_item_urls_rejects_non_https_and_duplicates():
    item = {
        "page_url": "http://insecure.example/1",
        "other_sources": [
            {"url": "https://secure.example/2"},
            {"url": "http://insecure.example/3"},
            {"url": "https://secure.example/2"},
        ],
    }
    assert _picimagesearch_item_urls("iqdb", item) == [
        ("https://secure.example/2", "Reverse-image match page reported by iqdb.")
    ]
    assert _picimagesearch_item_urls("unreviewed-engine", item) == []


def test_picimagesearch_pinned_constants():
    driver = _load_driver()
    assert driver.PINNED_COMMIT == "784713e546273a09aae4b247a8b6f798825efafa"
    assert driver.HONEST_UA == "Aletheia/0.9.0 (picimagesearch)"
    assert driver.PINNED_COMMIT[:12] in PicImageSearchAdapter.descriptor.version_pin
    assert driver.GATHER_TIMEOUT_SECONDS == 150.0
    assert driver.HARD_DEADLINE_SECONDS == 210.0
    assert driver.MAX_UPLOAD_BYTES == 12 * 1024 * 1024
