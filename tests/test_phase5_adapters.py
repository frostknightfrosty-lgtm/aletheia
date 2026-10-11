import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.social_geo_image import (
    DeepFaceAdapter, InsightFaceAdapter, InstaloaderAdapter,
    OverpassAdapter, RedditAPIAdapter, SunCalcAdapter, YouTubeAPIAdapter,
)
from aletheia.adapters.registry import phase5_adapters
from aletheia.core.audit import AuditLogger
from aletheia.core.models import AdapterRunRequest, Seed, SeedType, EntityType


def req(kind, value, assertion="authorized Phase 5 test"):
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=kind, value=value), legal_only=True,
                             authorization_assertion=assertion)


def test_phase5_registry_contains_seven_new_adapters():
    registry = phase5_adapters()
    expected = {"instaloader", "reddit-api", "youtube-api", "overpass", "suncalc", "deepface", "insightface"}
    assert expected <= set(registry)
    assert len(registry) == 26


def test_phase5_authorization_gate(monkeypatch, tmp_path):
    import aletheia.core.adapters as core_adapters
    called = False
    def fake_run_docker(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("Docker must not execute before authorization")
    monkeypatch.setattr(core_adapters, "run_docker", fake_run_docker)
    for adapter, kind, value in [
        (InstaloaderAdapter(), SeedType.USERNAME, "alice"),
        (RedditAPIAdapter(), SeedType.USERNAME, "alice"),
        (YouTubeAPIAdapter(), SeedType.USERNAME, "alice"),
        (OverpassAdapter(), SeedType.GEOLOCATION, "51.5,-0.1"),
    ]:
        request=AdapterRunRequest(run_id=uuid4(),seed=Seed(type=kind,value=value),legal_only=True,authorization_assertion=None)
        with pytest.raises(ValueError, match="authorization_assertion"):
            adapter.run(request, tmp_path / adapter.descriptor.name, AuditLogger(tmp_path / "audit.jsonl"))
    assert called is False


@parser_test('instaloader')
def test_instaloader_parser():
    payload=json.dumps({"username":"alice","profile_url":"https://www.instagram.com/alice/","full_name":"Alice","followers":12,"is_private":False})
    result=InstaloaderAdapter().parse(req(SeedType.USERNAME,"alice"),Path('.'),payload,'',0)
    assert any(f.entity_type==EntityType.SOCIAL_ACCOUNT and f.value.endswith('/alice/') for f in result.findings)


@parser_test('reddit-api')
def test_reddit_parser():
    payload=json.dumps({"data":{"name":"alice","created_utc":1,"link_karma":10,"comment_karma":20}})
    result=RedditAPIAdapter().parse(req(SeedType.USERNAME,"alice"),Path('.'),payload,'',0)
    assert any(f.entity_type==EntityType.URL and 'reddit.com/user/alice' in f.value for f in result.findings)


@parser_test('youtube-api')
def test_youtube_parser():
    payload=json.dumps({"items":[{"id":"UC123","snippet":{"title":"Alice Channel"},"statistics":{"subscriberCount":"10"}}]})
    result=YouTubeAPIAdapter().parse(req(SeedType.USERNAME,"alice"),Path('.'),payload,'',0)
    assert any(f.entity_type==EntityType.SOCIAL_ACCOUNT and 'youtube.com/channel/UC123' in f.value for f in result.findings)


@parser_test('overpass')
def test_overpass_parser():
    payload=json.dumps({"elements":[{"type":"node","id":42,"lat":51.5,"lon":-0.1,"tags":{"name":"Test Cafe","amenity":"cafe"}}]})
    result=OverpassAdapter().parse(req(SeedType.GEOLOCATION,"51.500000,-0.100000"),Path('.'),payload,'',0)
    assert any(f.entity_type==EntityType.PLACE and f.value=='Test Cafe' for f in result.findings)


@parser_test('suncalc')
def test_suncalc_parser():
    payload=json.dumps({"timestamp":"2026-10-08T12:00:00.000Z","sun_altitude":0.5,"sun_azimuth":1.2,"sun_times":{"sunrise":"x","sunset":"y"}})
    result=SunCalcAdapter().parse(req(SeedType.GEOLOCATION,"51.5,-0.1"),Path('.'),payload,'',0)
    assert any(f.entity_type==EntityType.GEOLOCATION for f in result.findings)


@parser_test('deepface')
def test_deepface_parser_no_identity_claim():
    payload=json.dumps({"faces":[{"facial_area":{"x":1,"y":2,"w":10,"h":10},"confidence":0.99}]})
    result=DeepFaceAdapter().parse(req(SeedType.IMAGE,"/tmp/sample.jpg"),Path('.'),payload,'',0)
    assert any(f.entity_type==EntityType.FACE for f in result.findings)
    assert all('identity' not in f.attributes for f in result.findings)


@parser_test('insightface')
def test_insightface_parser():
    payload=json.dumps({"faces":[{"bbox":[1,2,3,4],"det_score":0.88}]})
    result=InsightFaceAdapter().parse(req(SeedType.IMAGE,"/tmp/sample.jpg"),Path('.'),payload,'',0)
    assert any(f.entity_type==EntityType.FACE for f in result.findings)
